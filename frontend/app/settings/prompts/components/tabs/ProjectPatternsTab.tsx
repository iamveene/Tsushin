'use client'

import React, { useState, useEffect, FormEvent } from 'react'
import client, { ProjectCommandPattern } from '@/lib/client'
import { ConfirmDialog, RegexTester, Tooltip, InfoIcon } from '../ui'

interface ProjectPatternFormData {
  command_type: string
  language_code: string
  pattern: string
  response_template: string
  is_active: boolean
}

const COMMAND_TYPES = ['enter', 'exit', 'upload', 'list', 'help']
const LANGUAGES = ['en', 'pt', 'es', 'fr', 'de', 'it', 'ja', 'ko', 'zh']

interface ProjectPatternsTabProps {
  canWrite: boolean
  showToast: (type: 'success' | 'error', message: string) => void
}

export function ProjectPatternsTab({ canWrite, showToast }: ProjectPatternsTabProps) {
  const [patterns, setPatterns] = useState<ProjectCommandPattern[]>([])
  const [loading, setLoading] = useState(true)

  // Filter state
  const [searchQuery, setSearchQuery] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState<boolean | ''>('')

  // Modal state
  const [showModal, setShowModal] = useState(false)
  const [editingPattern, setEditingPattern] = useState<ProjectCommandPattern | null>(null)
  const [formData, setFormData] = useState<ProjectPatternFormData>({
    command_type: 'enter',
    language_code: 'en',
    pattern: '',
    response_template: '',
    is_active: true
  })
  const [saving, setSaving] = useState(false)
  const [patternError, setPatternError] = useState<string | null>(null)

  // Delete confirmation state
  const [deleteConfirm, setDeleteConfirm] = useState<{ id: number, type: string } | null>(null)

  useEffect(() => {
    loadPatterns()
  }, [])

  async function loadPatterns() {
    setLoading(true)
    try {
      const data = await client.getProjectPatterns()
      setPatterns(data)
    } catch (error) {
      console.error('Failed to load patterns:', error)
      showToast('error', 'Failed to load project patterns')
    } finally {
      setLoading(false)
    }
  }

  // Client-side filtering
  const filteredPatterns = patterns.filter(p => {
    const matchesSearch = !searchQuery ||
      p.command_type.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.pattern.toLowerCase().includes(searchQuery.toLowerCase())
    const matchesType = !typeFilter || p.command_type === typeFilter
    const matchesStatus = statusFilter === '' || p.is_active === statusFilter
    return matchesSearch && matchesType && matchesStatus
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
    setEditingPattern(null)
    setFormData({
      command_type: 'enter',
      language_code: 'en',
      pattern: '',
      response_template: '',
      is_active: true
    })
    setPatternError(null)
    setShowModal(true)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  function openEditModal(pattern: ProjectCommandPattern) {
    setEditingPattern(pattern)
    setFormData({
      command_type: pattern.command_type,
      language_code: pattern.language_code,
      pattern: pattern.pattern,
      response_template: pattern.response_template,
      is_active: pattern.is_active
    })
    setPatternError(null)
    setShowModal(true)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function handleSave(e: FormEvent) {
    e.preventDefault()

    if (!formData.pattern.trim() || !formData.response_template.trim()) {
      showToast('error', 'Pattern and response template are required')
      return
    }

    if (!validatePattern(formData.pattern)) {
      showToast('error', 'Invalid regex pattern')
      return
    }

    setSaving(true)
    try {
      const payload = {
        command_type: formData.command_type,
        language_code: formData.language_code,
        pattern: formData.pattern,
        response_template: formData.response_template,
        is_active: formData.is_active
      }

      if (editingPattern) {
        await client.updateProjectPattern(editingPattern.id, payload)
        showToast('success', 'Project pattern updated successfully')
      } else {
        await client.createProjectPattern(payload)
        showToast('success', 'Project pattern created successfully')
      }
      setShowModal(false)
      await loadPatterns()
    } catch (error: unknown) {
      console.error('Failed to save:', error)
      const errorMessage = error instanceof Error ? error.message : 'Failed to save project pattern'
      showToast('error', errorMessage)
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete() {
    if (!deleteConfirm) return

    try {
      await client.deleteProjectPattern(deleteConfirm.id)
      showToast('success', 'Project pattern deleted successfully')
      setDeleteConfirm(null)
      await loadPatterns()
    } catch (error: unknown) {
      console.error('Failed to delete:', error)
      const errorMessage = error instanceof Error ? error.message : 'Failed to delete project pattern'
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
          placeholder="Search patterns..."
          className="flex-1 min-w-[200px] px-4 py-2 bg-tsushin-dark/50 border border-tsushin-border rounded-lg text-white placeholder-tsushin-slate focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
        />
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="px-4 py-2 bg-tsushin-dark/50 border border-tsushin-border rounded-lg text-white focus:border-teal-500"
        >
          <option value="">All Types</option>
          {COMMAND_TYPES.map(type => (
            <option key={type} value={type}>{type}</option>
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
            + New Pattern
          </button>
        )}
      </div>

      {/* Results count */}
      <div className="text-sm text-tsushin-slate mb-4">
        Showing {filteredPatterns.length} of {patterns.length} patterns
      </div>

      {/* Table */}
      {loading ? (
        <div className="text-center py-8 text-tsushin-slate">
          Loading project patterns...
        </div>
      ) : filteredPatterns.length === 0 ? (
        <div className="text-center py-8 text-tsushin-slate">
          No project patterns found
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-tsushin-border">
                <th className="text-left py-3 px-4 text-sm font-medium text-white">Command Type</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-white">Language</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-white">Pattern</th>
                <th className="text-center py-3 px-4 text-sm font-medium text-white">Status</th>
                <th className="text-center py-3 px-4 text-sm font-medium text-white">Type</th>
                {canWrite && <th className="text-right py-3 px-4 text-sm font-medium text-white">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {filteredPatterns.map((pattern) => (
                <tr key={pattern.id} className="border-b border-tsushin-border/50 hover:bg-tsushin-dark/30">
                  <td className="py-3 px-4 text-sm text-white font-medium">
                    {pattern.command_type}
                  </td>
                  <td className="py-3 px-4 text-sm text-tsushin-slate uppercase">
                    {pattern.language_code}
                  </td>
                  <td className="py-3 px-4 text-sm text-tsushin-slate font-mono max-w-xs truncate">
                    {pattern.pattern}
                  </td>
                  <td className="py-3 px-4 text-center">
                    {pattern.is_active ? (
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
                    {pattern.is_system ? (
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
                      {!pattern.is_system && (
                        <button
                          onClick={() => openEditModal(pattern)}
                          className="text-teal-400 hover:text-teal-300 text-sm font-medium transition-colors"
                        >
                          Edit
                        </button>
                      )}
                      <button
                        onClick={() => setDeleteConfirm({ id: pattern.id, type: pattern.command_type })}
                        disabled={pattern.is_system}
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
              {editingPattern ? 'Edit Project Pattern' : 'Create Project Pattern'}
            </h3>
            <form onSubmit={handleSave} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-white mb-2">Command Type *</label>
                  <select
                    value={formData.command_type}
                    onChange={(e) => setFormData({ ...formData, command_type: e.target.value })}
                    required
                    className="w-full px-4 py-2 bg-tsushin-deep border border-tsushin-border rounded-lg text-white focus:border-teal-500"
                  >
                    {COMMAND_TYPES.map(type => (
                      <option key={type} value={type}>{type}</option>
                    ))}
                  </select>
                </div>
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
                  placeholder="e.g., (enter|join|start)\s+(.+)"
                />
                {patternError && (
                  <p className="text-xs text-red-400 mt-1">Invalid regex: {patternError}</p>
                )}
                <RegexTester pattern={formData.pattern} placeholder="e.g., enter my-project" />
              </div>

              <div>
                <label className="block text-sm font-medium text-white mb-2 flex items-center gap-2">
                  Response Template *
                  <Tooltip content={
                    <div className="space-y-1">
                      <p className="font-medium">Template for the response message</p>
                      <p><code className="bg-tsushin-deep px-1 rounded">{'{project_name}'}</code> - Project name</p>
                      <p><code className="bg-tsushin-deep px-1 rounded">{'{user}'}</code> - User name</p>
                      <p><code className="bg-tsushin-deep px-1 rounded">{'{$1}'}</code> - First capture group</p>
                      <p><code className="bg-tsushin-deep px-1 rounded">{'{$2}'}</code> - Second capture group</p>
                    </div>
                  }>
                    <InfoIcon />
                  </Tooltip>
                </label>
                <textarea
                  value={formData.response_template}
                  onChange={(e) => setFormData({ ...formData, response_template: e.target.value })}
                  required
                  rows={3}
                  className="w-full px-4 py-2 bg-tsushin-deep border border-tsushin-border rounded-lg text-white placeholder-tsushin-slate focus:border-teal-500 focus:ring-1 focus:ring-teal-500 font-mono"
                  placeholder="e.g., Entering project: {project_name}"
                />
              </div>

              <div className="flex items-center">
                <input
                  type="checkbox"
                  id="pattern_is_active"
                  checked={formData.is_active}
                  onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                  className="w-4 h-4 text-teal-500 bg-tsushin-deep border-tsushin-border rounded focus:ring-teal-500"
                />
                <label htmlFor="pattern_is_active" className="ml-2 text-sm text-white">
                  Pattern is active
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
                  {saving ? 'Saving...' : (editingPattern ? 'Update' : 'Create')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirmation */}
      <ConfirmDialog
        isOpen={!!deleteConfirm}
        title="Delete Project Pattern"
        message={`Are you sure you want to delete the "${deleteConfirm?.type}" pattern? This action cannot be undone.`}
        onConfirm={handleDelete}
        onCancel={() => setDeleteConfirm(null)}
      />
    </div>
  )
}
