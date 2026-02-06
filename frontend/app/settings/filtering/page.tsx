'use client'

/**
 * Message Filtering Settings Page
 * Configure system-level group filters and message routing
 *
 * These are the DEFAULT filters used when agents don't have their own trigger_group_filters.
 * Agent-specific filters are configured in the Agent Configuration Manager.
 */

import { useState, useEffect } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { api, Config } from '@/lib/client'
import Link from 'next/link'

export default function FilteringSettingsPage() {
  const { hasPermission } = useAuth()
  const [config, setConfig] = useState<Config | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Form state
  const [groupFilters, setGroupFilters] = useState<string[]>([])
  const [numberFilters, setNumberFilters] = useState<string[]>([])
  const [groupKeywords, setGroupKeywords] = useState<string[]>([])
  const [dmAutoMode, setDmAutoMode] = useState(false)

  // Input states for adding new items
  const [groupFilterInput, setGroupFilterInput] = useState('')
  const [numberFilterInput, setNumberFilterInput] = useState('')
  const [keywordInput, setKeywordInput] = useState('')

  const canEdit = hasPermission('org.settings.write')

  useEffect(() => {
    loadConfig()
  }, [])

  const loadConfig = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getConfig()
      setConfig(data)
      setGroupFilters(data.group_filters || [])
      setNumberFilters(data.number_filters || [])
      setGroupKeywords(data.group_keywords || [])
      setDmAutoMode(data.dm_auto_mode || false)
    } catch (err) {
      console.error('Failed to load config:', err)
      setError('Failed to load configuration')
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    setSuccess(false)
    setError(null)

    try {
      await api.updateConfig({
        group_filters: groupFilters,
        number_filters: numberFilters,
        group_keywords: groupKeywords,
        dm_auto_mode: dmAutoMode,
      })
      setSuccess(true)
      setTimeout(() => setSuccess(false), 3000)
    } catch (err) {
      console.error('Failed to save config:', err)
      setError('Failed to save configuration')
    } finally {
      setSaving(false)
    }
  }

  // Group filter helpers
  const addGroupFilter = () => {
    const filter = groupFilterInput.trim()
    if (filter && !groupFilters.includes(filter)) {
      setGroupFilters([...groupFilters, filter])
      setGroupFilterInput('')
    }
  }

  const removeGroupFilter = (filter: string) => {
    setGroupFilters(groupFilters.filter(f => f !== filter))
  }

  // Number filter helpers
  const addNumberFilter = () => {
    const filter = numberFilterInput.trim()
    if (filter && !numberFilters.includes(filter)) {
      setNumberFilters([...numberFilters, filter])
      setNumberFilterInput('')
    }
  }

  const removeNumberFilter = (filter: string) => {
    setNumberFilters(numberFilters.filter(f => f !== filter))
  }

  // Keyword helpers
  const addKeyword = () => {
    const keyword = keywordInput.trim()
    if (keyword && !groupKeywords.includes(keyword)) {
      setGroupKeywords([...groupKeywords, keyword])
      setKeywordInput('')
    }
  }

  const removeKeyword = (keyword: string) => {
    setGroupKeywords(groupKeywords.filter(k => k !== keyword))
  }

  if (!hasPermission('org.settings.write')) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-red-900 dark:text-red-100 mb-2">
            Access Denied
          </h3>
          <p className="text-sm text-red-800 dark:text-red-200">
            You don't have permission to view message filtering settings.
          </p>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-center h-64">
          <div className="text-lg text-gray-600 dark:text-gray-400">Loading configuration...</div>
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-2 text-sm text-tsushin-slate mb-2">
            <Link href="/settings" className="hover:text-teal-400 transition-colors">Settings</Link>
            <span>/</span>
            <span className="text-white">Message Filtering</span>
          </div>
          <h1 className="text-3xl font-display font-bold text-white">
            Message Filtering
          </h1>
          <p className="text-tsushin-slate mt-2">
            Configure system-level filters for message routing. These are the default filters used when agents don't have their own specific filters.
          </p>
        </div>

        {/* Phase 17: Deprecation Notice */}
        <div className="mb-8 p-4 bg-amber-500/10 border border-amber-500/30 rounded-xl">
          <div className="flex items-start gap-3">
            <svg className="w-6 h-6 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" /></svg>
            <div>
              <h3 className="text-lg font-semibold text-amber-400 mb-1">
                Moving to Per-Instance Configuration
              </h3>
              <p className="text-sm text-amber-200/80 mb-2">
                Message filtering is now configured per WhatsApp instance for better control.
                These global settings will be used as defaults for instances without their own configuration.
              </p>
              <Link
                href="/hub"
                className="inline-flex items-center gap-2 px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-sm font-medium transition-colors"
              >
                <span>Configure in Hub</span>
                <span>→</span>
              </Link>
            </div>
          </div>
        </div>

        {/* Success Message */}
        {success && (
          <div className="mb-6 bg-green-500/10 border border-green-500/30 rounded-lg p-4">
            <p className="text-sm text-green-400">
              Settings saved successfully! Changes will take effect on the next watcher restart or filter reload.
            </p>
          </div>
        )}

        {/* Error Message */}
        {error && (
          <div className="mb-6 bg-red-500/10 border border-red-500/30 rounded-lg p-4">
            <p className="text-sm text-red-400">{error}</p>
          </div>
        )}

        <div className="space-y-8">
          {/* Group Filters */}
          <div className="glass-card rounded-xl p-6">
            <h2 className="text-xl font-semibold text-white mb-2">
              Default Group Filters
            </h2>
            <p className="text-sm text-tsushin-slate mb-4">
              WhatsApp group names to monitor by default. Agents without their own group filters will use these.
              Messages from groups not in this list will be ignored (unless the agent has specific filters).
            </p>

            <div className="space-y-4">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={groupFilterInput}
                  onChange={(e) => setGroupFilterInput(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && addGroupFilter()}
                  placeholder="Enter group name (exact match)"
                  className="flex-1 bg-tsushin-deep border border-tsushin-slate/30 rounded-lg px-4 py-2 text-white placeholder-tsushin-slate/50 focus:outline-none focus:ring-2 focus:ring-teal-500/50"
                  disabled={!canEdit}
                />
                <button
                  onClick={addGroupFilter}
                  disabled={!canEdit || !groupFilterInput.trim()}
                  className="px-4 py-2 bg-teal-600 hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
                >
                  Add
                </button>
              </div>

              <div className="flex flex-wrap gap-2">
                {groupFilters.length === 0 ? (
                  <p className="text-sm text-tsushin-slate italic">No group filters configured. All groups will be monitored.</p>
                ) : (
                  groupFilters.map((filter) => (
                    <span
                      key={filter}
                      className="inline-flex items-center gap-2 px-3 py-1 bg-teal-500/20 border border-teal-500/30 rounded-full text-sm text-teal-300"
                    >
                      {filter}
                      {canEdit && (
                        <button
                          onClick={() => removeGroupFilter(filter)}
                          className="text-teal-400 hover:text-red-400 transition-colors"
                        >
                          ×
                        </button>
                      )}
                    </span>
                  ))
                )}
              </div>
            </div>
          </div>

          {/* Number Filters */}
          <div className="glass-card rounded-xl p-6">
            <h2 className="text-xl font-semibold text-white mb-2">
              Number Filters (DM Allowlist)
            </h2>
            <p className="text-sm text-tsushin-slate mb-4">
              Phone numbers that are allowed to send direct messages to the agent.
              Format: Include country code (e.g., +5500000000001).
            </p>

            <div className="space-y-4">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={numberFilterInput}
                  onChange={(e) => setNumberFilterInput(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && addNumberFilter()}
                  placeholder="Enter phone number (e.g., +5500000000001)"
                  className="flex-1 bg-tsushin-deep border border-tsushin-slate/30 rounded-lg px-4 py-2 text-white placeholder-tsushin-slate/50 focus:outline-none focus:ring-2 focus:ring-teal-500/50"
                  disabled={!canEdit}
                />
                <button
                  onClick={addNumberFilter}
                  disabled={!canEdit || !numberFilterInput.trim()}
                  className="px-4 py-2 bg-teal-600 hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
                >
                  Add
                </button>
              </div>

              <div className="flex flex-wrap gap-2">
                {numberFilters.length === 0 ? (
                  <p className="text-sm text-tsushin-slate italic">No number filters configured.</p>
                ) : (
                  numberFilters.map((filter) => (
                    <span
                      key={filter}
                      className="inline-flex items-center gap-2 px-3 py-1 bg-purple-500/20 border border-purple-500/30 rounded-full text-sm text-purple-300"
                    >
                      {filter}
                      {canEdit && (
                        <button
                          onClick={() => removeNumberFilter(filter)}
                          className="text-purple-400 hover:text-red-400 transition-colors"
                        >
                          ×
                        </button>
                      )}
                    </span>
                  ))
                )}
              </div>
            </div>
          </div>

          {/* Group Keywords */}
          <div className="glass-card rounded-xl p-6">
            <h2 className="text-xl font-semibold text-white mb-2">
              Group Keywords
            </h2>
            <p className="text-sm text-tsushin-slate mb-4">
              Keywords that trigger agent responses in group chats (in addition to @mentions).
              Case-insensitive matching.
            </p>

            <div className="space-y-4">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={keywordInput}
                  onChange={(e) => setKeywordInput(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && addKeyword()}
                  placeholder="Enter keyword"
                  className="flex-1 bg-tsushin-deep border border-tsushin-slate/30 rounded-lg px-4 py-2 text-white placeholder-tsushin-slate/50 focus:outline-none focus:ring-2 focus:ring-teal-500/50"
                  disabled={!canEdit}
                />
                <button
                  onClick={addKeyword}
                  disabled={!canEdit || !keywordInput.trim()}
                  className="px-4 py-2 bg-teal-600 hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
                >
                  Add
                </button>
              </div>

              <div className="flex flex-wrap gap-2">
                {groupKeywords.length === 0 ? (
                  <p className="text-sm text-tsushin-slate italic">No keywords configured. Only @mentions will trigger responses.</p>
                ) : (
                  groupKeywords.map((keyword) => (
                    <span
                      key={keyword}
                      className="inline-flex items-center gap-2 px-3 py-1 bg-amber-500/20 border border-amber-500/30 rounded-full text-sm text-amber-300"
                    >
                      {keyword}
                      {canEdit && (
                        <button
                          onClick={() => removeKeyword(keyword)}
                          className="text-amber-400 hover:text-red-400 transition-colors"
                        >
                          ×
                        </button>
                      )}
                    </span>
                  ))
                )}
              </div>
            </div>
          </div>

          {/* DM Settings */}
          <div className="glass-card rounded-xl p-6">
            <h2 className="text-xl font-semibold text-white mb-2">
              DM Settings
            </h2>
            <p className="text-sm text-tsushin-slate mb-4">
              Configure how direct messages are handled.
            </p>

            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <input
                  type="checkbox"
                  id="dmAutoMode"
                  checked={dmAutoMode}
                  onChange={(e) => setDmAutoMode(e.target.checked)}
                  className="w-5 h-5 rounded border-tsushin-slate/30 bg-tsushin-deep text-teal-500 focus:ring-teal-500/50"
                  disabled={!canEdit}
                />
                <label htmlFor="dmAutoMode" className="text-white">
                  DM Auto Mode
                </label>
              </div>
              <p className="text-xs text-tsushin-slate -mt-2 ml-8">
                When enabled, automatically respond to DMs from <strong className="text-white">unknown senders</strong> (not in Contacts).
                Known contacts are controlled by their individual <code className="text-teal-400">is_dm_trigger</code> setting in{' '}
                <Link href="/agents/contacts" className="text-teal-400 hover:underline">Studio → Contacts</Link>.
              </p>
            </div>
          </div>

          {/* Save Button */}
          {canEdit && (
            <div className="flex justify-end gap-4">
              <button
                onClick={loadConfig}
                className="px-6 py-2 bg-tsushin-deep hover:bg-tsushin-slate/30 border border-tsushin-slate/30 text-white rounded-lg transition-colors"
              >
                Reset
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="px-6 py-2 bg-teal-600 hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors"
              >
                {saving ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          )}

          {/* Info Card */}
          <div className="glass-card rounded-xl p-6 border-blue-500/30">
            <h3 className="text-lg font-semibold text-white mb-2">
              How Message Filtering Works
            </h3>
            <div className="text-sm text-tsushin-slate space-y-2">
              <p>
                <strong className="text-white">For Groups:</strong> Messages are processed if the group name matches any filter AND (the agent is @mentioned OR the message contains a keyword).
              </p>
              <p>
                <strong className="text-white">For DMs:</strong> Known contacts trigger based on their <code className="text-teal-400">is_dm_trigger</code> setting (configurable in Studio → Contacts).
                Unknown senders only trigger if DM Auto Mode is enabled OR they're in the Number Filters list.
              </p>
              <p>
                <strong className="text-white">Agent-specific filters:</strong> Individual agents can override these defaults with their own <code className="text-teal-400">trigger_group_filters</code> in the{' '}
                <Link href="/agents" className="text-teal-400 hover:underline">Agent Studio</Link>.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
