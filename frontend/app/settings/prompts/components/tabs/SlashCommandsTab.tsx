'use client'

import React, { useState, useEffect, FormEvent } from 'react'
import client, { SlashCommandDetail } from '@/lib/client'
import { ConfirmDialog, RegexTester, Tooltip, InfoIcon } from '../ui'

interface SlashCommandFormData {
  category: string
  command_name: string
  language_code: string
  pattern: string
  aliases: string
  description: string
  handler_type: string
  is_enabled: boolean
}

const COMMAND_CATEGORIES = ['project', 'agent', 'tool', 'memory', 'system']
const LANGUAGES = ['en', 'pt', 'es', 'fr', 'de', 'it', 'ja', 'ko', 'zh']
const HANDLER_TYPES = ['built-in', 'custom', 'webhook']

interface SlashCommandsTabProps {
  canWrite: boolean
  showToast: (type: 'success' | 'error', message: string) => void
}

export function SlashCommandsTab({ canWrite, showToast }: SlashCommandsTabProps) {
  const [commands, setCommands] = useState<SlashCommandDetail[]>([])
  const [loading, setLoading] = useState(true)

  // Filter state
  const [searchQuery, setSearchQuery] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState<boolean | ''>('')

  // Modal state
  const [showModal, setShowModal] = useState(false)
  const [editingCommand, setEditingCommand] = useState<SlashCommandDetail | null>(null)
  const [formData, setFormData] = useState<SlashCommandFormData>({
    category: 'project',
    command_name: '',
    language_code: 'en',
    pattern: '',
    aliases: '',
    description: '',
    handler_type: 'built-in',
    is_enabled: true
  })
  const [saving, setSaving] = useState(false)
  const [patternError, setPatternError] = useState<string | null>(null)

  // Delete confirmation state
  const [deleteConfirm, setDeleteConfirm] = useState<{ id: number, name: string } | null>(null)

  useEffect(() => {
    loadCommands()
  }, [])

  async function loadCommands() {
    setLoading(true)
    try {
      const data = await client.getSlashCommands()
      setCommands(data)
    } catch (error) {
      console.error('Failed to load commands:', error)
      showToast('error', 'Failed to load slash commands')
    } finally {
      setLoading(false)
    }
  }

  // Client-side filtering
  const filteredCommands = commands.filter(cmd => {
    const matchesSearch = !searchQuery ||
      cmd.command_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      cmd.category.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (cmd.description && cmd.description.toLowerCase().includes(searchQuery.toLowerCase()))
    const matchesCategory = !categoryFilter || cmd.category === categoryFilter
    const matchesStatus = statusFilter === '' || cmd.is_enabled === statusFilter
    return matchesSearch && matchesCategory && matchesStatus
  })

  function validatePattern(pattern: string): boolean {
    try {
      new RegExp(pattern)
      setPatternError(null)
      return true
    } catch (e) {
      setPatternError((e as Error).message)
      return false
    }
  }

  function openCreateModal() {
    setEditingCommand(null)
    setFormData({
      category: 'project',
      command_name: '',
      language_code: 'en',
      pattern: '',
      aliases: '',
      description: '',
      handler_type: 'built-in',
      is_enabled: true
    })
    setPatternError(null)
    setShowModal(true)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  function openEditModal(cmd: SlashCommandDetail) {
    setEditingCommand(cmd)
    setFormData({
      category: cmd.category,
      command_name: cmd.command_name,
      language_code: cmd.language_code,
      pattern: cmd.pattern,
      aliases: cmd.aliases?.join(', ') || '',
      description: cmd.description || '',
      handler_type: cmd.handler_type,
      is_enabled: cmd.is_enabled
    })
    setPatternError(null)
    setShowModal(true)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function handleSave(e: FormEvent) {
    e.preventDefault()

    if (!formData.command_name.trim() || !formData.pattern.trim()) {
      showToast('error', 'Command name and pattern are required')
      return
    }

    if (!validatePattern(formData.pattern)) {
      showToast('error', 'Invalid regex pattern')
      return
    }

    const aliasesArray = formData.aliases
      .split(',')
      .map(a => a.trim())
      .filter(a => a.length > 0)

    setSaving(true)
    try {
      const payload = {
        category: formData.category,
        command_name: formData.command_name,
        language_code: formData.language_code,
        pattern: formData.pattern,
        aliases: aliasesArray,
        description: formData.description || undefined,
        handler_type: formData.handler_type,
        is_enabled: formData.is_enabled
      }

      if (editingCommand) {
        await client.updateSlashCommand(editingCommand.id, payload)
        showToast('success', 'Slash command updated successfully')
      } else {
        await client.createSlashCommand(payload)
        showToast('success', 'Slash command created successfully')
      }
      setShowModal(false)
      await loadCommands()
    } catch (error: unknown) {
      console.error('Failed to save:', error)
      const errorMessage = error instanceof Error ? error.message : 'Failed to save slash command'
      showToast('error', errorMessage)
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete() {
    if (!deleteConfirm) return

    try {
      await client.deleteSlashCommand(deleteConfirm.id)
      showToast('success', 'Slash command deleted successfully')
      setDeleteConfirm(null)
      await loadCommands()
    } catch (error: unknown) {
      console.error('Failed to delete:', error)
      const errorMessage = error instanceof Error ? error.message : 'Failed to delete slash command'
      showToast('error', errorMessage)
    }
  }

  return (
    <div className="glass-card rounded-xl p-6">
      {/* Header with Filters and Create Button */}
      <div className="flex flex-wrap items-center gap-3 mb-6">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search commands..."
          className="flex-1 min-w-[200px] px-4 py-2 bg-tsushin-dark/50 border border-tsushin-border rounded-lg text-white placeholder-tsushin-slate focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
        />
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="px-4 py-2 bg-tsushin-dark/50 border border-tsushin-border rounded-lg text-white focus:border-teal-500"
        >
          <option value="">All Categories</option>
          {COMMAND_CATEGORIES.map(cat => (
            <option key={cat} value={cat}>{cat}</option>
          ))}
        </select>
        <select
          value={statusFilter === '' ? '' : statusFilter.toString()}
          onChange={(e) => setStatusFilter(e.target.value === '' ? '' : e.target.value === 'true')}
          className="px-4 py-2 bg-tsushin-dark/50 border border-tsushin-border rounded-lg text-white focus:border-teal-500"
        >
          <option value="">All Status</option>
          <option value="true">Active</option>
          <option value="false">Inactive</option>
        </select>
        {canWrite && (
          <button
            onClick={openCreateModal}
            className="px-4 py-2 bg-teal-500 hover:bg-teal-600 text-white rounded-lg font-medium transition-colors whitespace-nowrap"
          >
            + New Command
          </button>
        )}
      </div>

      {/* Results count */}
      <div className="text-sm text-tsushin-slate mb-4">
        Showing {filteredCommands.length} of {commands.length} commands
      </div>

      {/* Table */}
      {loading ? (
        <div className="text-center py-8 text-tsushin-slate">
          Loading slash commands...
        </div>
      ) : filteredCommands.length === 0 ? (
        <div className="text-center py-8 text-tsushin-slate">
          No slash commands found
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-tsushin-border">
                <th className="text-left py-3 px-4 text-sm font-medium text-white">Command</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-white">Category</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-white">Pattern</th>
                <th className="text-center py-3 px-4 text-sm font-medium text-white">Status</th>
                <th className="text-center py-3 px-4 text-sm font-medium text-white">Type</th>
                {canWrite && <th className="text-right py-3 px-4 text-sm font-medium text-white">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {filteredCommands.map((cmd) => (
                <tr key={cmd.id} className="border-b border-tsushin-border/50 hover:bg-tsushin-dark/30">
                  <td className="py-3 px-4 text-sm text-white font-medium font-mono">
                    {cmd.command_name}
                  </td>
                  <td className="py-3 px-4 text-sm text-tsushin-slate">
                    {cmd.category}
                  </td>
                  <td className="py-3 px-4 text-sm text-tsushin-slate font-mono max-w-xs truncate">
                    {cmd.pattern}
                  </td>
                  <td className="py-3 px-4 text-center">
                    {cmd.is_enabled ? (
                      <span className="inline-flex items-center px-2 py-1 rounded-full text-xs bg-green-500/20 text-green-400">
                        Active
                      </span>
                    ) : (
                      <span className="inline-flex items-center px-2 py-1 rounded-full text-xs bg-gray-500/20 text-gray-400">
                        Inactive
                      </span>
                    )}
                  </td>
                  <td className="py-3 px-4 text-center">
                    {cmd.is_system ? (
                      <span className="inline-flex items-center px-2 py-1 rounded-full text-xs bg-purple-500/20 text-purple-400">
                        System
                      </span>
                    ) : (
                      <span className="inline-flex items-center px-2 py-1 rounded-full text-xs bg-teal-500/20 text-teal-400">
                        Custom
                      </span>
                    )}
                  </td>
                  {canWrite && (
                    <td className="py-3 px-4 text-right space-x-2">
                      {!cmd.is_system && (
                        <button
                          onClick={() => openEditModal(cmd)}
                          className="text-teal-400 hover:text-teal-300 text-sm font-medium transition-colors"
                        >
                          Edit
                        </button>
                      )}
                      <button
                        onClick={() => setDeleteConfirm({ id: cmd.id, name: cmd.command_name })}
                        disabled={cmd.is_system}
                        className="text-red-400 hover:text-red-300 text-sm font-medium disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                      >
                        Delete
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create/Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 overflow-y-auto py-8" onClick={() => setShowModal(false)}>
          <div className="glass-card rounded-xl p-6 max-w-2xl w-full mx-4" onClick={e => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-white mb-4">
              {editingCommand ? 'Edit Slash Command' : 'Create Slash Command'}
            </h3>
            <form onSubmit={handleSave} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-white mb-2">Command Name *</label>
                  <input
                    type="text"
                    value={formData.command_name}
                    onChange={(e) => setFormData({ ...formData, command_name: e.target.value })}
                    maxLength={50}
                    required
                    className="w-full px-4 py-2 bg-tsushin-deep border border-tsushin-border rounded-lg text-white placeholder-tsushin-slate focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
                    placeholder="e.g., help, status"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-white mb-2">Category *</label>
                  <select
                    value={formData.category}
                    onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                    required
                    className="w-full px-4 py-2 bg-tsushin-deep border border-tsushin-border rounded-lg text-white focus:border-teal-500"
                  >
                    {COMMAND_CATEGORIES.map(cat => (
                      <option key={cat} value={cat}>{cat}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-white mb-2">Language</label>
                  <select
                    value={formData.language_code}
                    onChange={(e) => setFormData({ ...formData, language_code: e.target.value })}
                    className="w-full px-4 py-2 bg-tsushin-deep border border-tsushin-border rounded-lg text-white focus:border-teal-500"
                  >
                    {LANGUAGES.map(lang => (
                      <option key={lang} value={lang}>{lang.toUpperCase()}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-white mb-2">Handler Type</label>
                  <select
                    value={formData.handler_type}
                    onChange={(e) => setFormData({ ...formData, handler_type: e.target.value })}
                    className="w-full px-4 py-2 bg-tsushin-deep border border-tsushin-border rounded-lg text-white focus:border-teal-500"
                  >
                    {HANDLER_TYPES.map(type => (
                      <option key={type} value={type}>{type}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-white mb-2 flex items-center gap-2">
                  Pattern (Regex) *
                  <Tooltip content={
                    <div className="space-y-1">
                      <p className="font-medium">Regex pattern to match user input</p>
                      <p><code className="bg-tsushin-deep px-1 rounded">^</code> - Start of text</p>
                      <p><code className="bg-tsushin-deep px-1 rounded">$</code> - End of text</p>
                      <p><code className="bg-tsushin-deep px-1 rounded">(a|b)</code> - Match a OR b</p>
                      <p><code className="bg-tsushin-deep px-1 rounded">(.+)</code> - Capture group</p>
                      <p><code className="bg-tsushin-deep px-1 rounded">\s+</code> - Whitespace</p>
                    </div>
                  }>
                    <InfoIcon />
                  </Tooltip>
                </label>
                <input
                  type="text"
                  value={formData.pattern}
                  onChange={(e) => {
                    setFormData({ ...formData, pattern: e.target.value })
                    validatePattern(e.target.value)
                  }}
                  required
                  className={`w-full px-4 py-2 bg-tsushin-deep border rounded-lg text-white placeholder-tsushin-slate focus:ring-1 font-mono ${
                    patternError ? 'border-red-500 focus:border-red-500 focus:ring-red-500' : 'border-tsushin-border focus:border-teal-500 focus:ring-teal-500'
                  }`}
                  placeholder="e.g., ^/(help|h)$"
                />
                {patternError && (
                  <p className="text-xs text-red-400 mt-1">Invalid regex: {patternError}</p>
                )}
                <RegexTester pattern={formData.pattern} placeholder="e.g., /help or /h" />
              </div>

              <div>
                <label className="block text-sm font-medium text-white mb-2">Aliases (comma-separated)</label>
                <input
                  type="text"
                  value={formData.aliases}
                  onChange={(e) => setFormData({ ...formData, aliases: e.target.value })}
                  className="w-full px-4 py-2 bg-tsushin-deep border border-tsushin-border rounded-lg text-white placeholder-tsushin-slate focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
                  placeholder="e.g., h, ?"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-white mb-2">Description</label>
                <textarea
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  rows={2}
                  className="w-full px-4 py-2 bg-tsushin-deep border border-tsushin-border rounded-lg text-white placeholder-tsushin-slate focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
                  placeholder="Describe what this command does..."
                />
              </div>

              <div className="flex items-center">
                <input
                  type="checkbox"
                  id="is_enabled"
                  checked={formData.is_enabled}
                  onChange={(e) => setFormData({ ...formData, is_enabled: e.target.checked })}
                  className="w-4 h-4 text-teal-500 bg-tsushin-deep border-tsushin-border rounded focus:ring-teal-500"
                />
                <label htmlFor="is_enabled" className="ml-2 text-sm text-white">
                  Command is active
                </label>
              </div>

              <div className="flex justify-end space-x-3 pt-4">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 text-tsushin-slate hover:text-white transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving || !!patternError}
                  className="px-6 py-2 bg-teal-500 hover:bg-teal-600 text-white rounded-lg font-medium transition-colors disabled:opacity-50"
                >
                  {saving ? 'Saving...' : (editingCommand ? 'Update' : 'Create')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirmation */}
      <ConfirmDialog
        isOpen={!!deleteConfirm}
        title="Delete Slash Command"
        message={`Are you sure you want to delete "/${deleteConfirm?.name}"? This action cannot be undone.`}
        onConfirm={handleDelete}
        onCancel={() => setDeleteConfirm(null)}
      />
    </div>
  )
}
