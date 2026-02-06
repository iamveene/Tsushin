'use client'

import React, { useState, useEffect } from 'react'
import client, { PromptConfig } from '@/lib/client'

interface GlobalConfigTabProps {
  canWrite: boolean
  showToast: (type: 'success' | 'error', message: string) => void
}

export function GlobalConfigTab({ canWrite, showToast }: GlobalConfigTabProps) {
  const [config, setConfig] = useState<PromptConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [editedConfig, setEditedConfig] = useState<Partial<PromptConfig>>({})

  useEffect(() => {
    loadConfig()
  }, [])

  async function loadConfig() {
    setLoading(true)
    try {
      const data = await client.getPromptConfig()
      setConfig(data)
      setEditedConfig({})
    } catch (error) {
      console.error('Failed to load config:', error)
      showToast('error', 'Failed to load configuration')
    } finally {
      setLoading(false)
    }
  }

  async function handleSave() {
    if (!canWrite || !Object.keys(editedConfig).length) return

    setSaving(true)
    try {
      const updated = await client.updatePromptConfig(editedConfig)
      setConfig(updated)
      setEditedConfig({})
      showToast('success', 'Configuration saved successfully')
    } catch (error) {
      console.error('Failed to save config:', error)
      showToast('error', 'Failed to save configuration')
    } finally {
      setSaving(false)
    }
  }

  function handleReset() {
    setEditedConfig({})
  }

  const hasChanges = Object.keys(editedConfig).length > 0

  if (loading) {
    return (
      <div className="glass-card rounded-xl p-8">
        <div className="flex items-center justify-center">
          <div className="text-tsushin-slate">Loading configuration...</div>
        </div>
      </div>
    )
  }

  if (!config) {
    return (
      <div className="glass-card rounded-xl p-8">
        <div className="text-center text-tsushin-slate">
          Failed to load configuration
        </div>
      </div>
    )
  }

  const currentSystemPrompt = editedConfig.system_prompt ?? config.system_prompt
  const currentResponseTemplate = editedConfig.response_template ?? config.response_template

  return (
    <div className="glass-card rounded-xl p-6">
      <div className="space-y-6">
        {/* System Prompt */}
        <div>
          <label className="block text-sm font-medium text-white mb-2">
            Global System Prompt
          </label>
          <p className="text-sm text-tsushin-slate mb-3">
            Default system prompt used when agents don't have custom prompts configured.
          </p>
          <textarea
            value={currentSystemPrompt}
            onChange={(e) => setEditedConfig({ ...editedConfig, system_prompt: e.target.value })}
            disabled={!canWrite}
            rows={12}
            className="w-full px-4 py-3 bg-tsushin-deep border border-tsushin-border rounded-lg text-white placeholder-tsushin-slate focus:border-teal-500 focus:ring-1 focus:ring-teal-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-mono text-sm"
            placeholder="Enter system prompt..."
          />
        </div>

        {/* Response Template */}
        <div>
          <label className="block text-sm font-medium text-white mb-2">
            Response Template
          </label>
          <p className="text-sm text-tsushin-slate mb-3">
            Template for formatting AI responses. Use {'{'}{'{'} answer {'}'}{'}'}  as placeholder.
          </p>
          <textarea
            value={currentResponseTemplate}
            onChange={(e) => setEditedConfig({ ...editedConfig, response_template: e.target.value })}
            disabled={!canWrite}
            rows={4}
            className="w-full px-4 py-3 bg-tsushin-deep border border-tsushin-border rounded-lg text-white placeholder-tsushin-slate focus:border-teal-500 focus:ring-1 focus:ring-teal-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-mono text-sm"
            placeholder="{{answer}}"
          />
        </div>

        {/* Actions */}
        {canWrite && (
          <div className="flex items-center justify-end space-x-3 pt-4 border-t border-tsushin-border">
            <button
              onClick={handleReset}
              disabled={!hasChanges || saving}
              className="px-4 py-2 text-sm font-medium text-tsushin-slate hover:text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Reset Changes
            </button>
            <button
              onClick={handleSave}
              disabled={!hasChanges || saving}
              className="px-6 py-2 bg-teal-500 hover:bg-teal-600 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving ? 'Saving...' : 'Save Configuration'}
            </button>
          </div>
        )}

        {/* Last Updated */}
        {config.updated_at && (
          <div className="text-xs text-tsushin-slate text-right">
            Last updated: {new Date(config.updated_at).toLocaleString()}
          </div>
        )}
      </div>
    </div>
  )
}
