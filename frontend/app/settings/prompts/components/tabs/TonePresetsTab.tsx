'use client'

import React, { useState, useEffect, FormEvent } from 'react'
import client, { TonePreset } from '@/lib/client'
import { ConfirmDialog } from '../ui'

interface TonePresetFormData {
  name: string
  description: string
}

interface TonePresetsTabProps {
  canWrite: boolean
  showToast: (type: 'success' | 'error', message: string) => void
}

export function TonePresetsTab({ canWrite, showToast }: TonePresetsTabProps) {
  const [presets, setPresets] = useState<TonePreset[]>([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')

  // Modal state
  const [showModal, setShowModal] = useState(false)
  const [editingPreset, setEditingPreset] = useState<TonePreset | null>(null)
  const [formData, setFormData] = useState<TonePresetFormData>({ name: '', description: '' })
  const [saving, setSaving] = useState(false)

  // Delete confirmation state
  const [deleteConfirm, setDeleteConfirm] = useState<{ id: number, name: string } | null>(null)

  useEffect(() => {
    loadPresets()
  }, [])

  async function loadPresets() {
    setLoading(true)
    try {
      const data = await client.getTonePresets(searchQuery || undefined)
      setPresets(data)
    } catch (error) {
      console.error('Failed to load tone presets:', error)
      showToast('error', 'Failed to load tone presets')
    } finally {
      setLoading(false)
    }
  }

  function openCreateModal() {
    setEditingPreset(null)
    setFormData({ name: '', description: '' })
    setShowModal(true)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  function openEditModal(preset: TonePreset) {
    setEditingPreset(preset)
    setFormData({ name: preset.name, description: preset.description })
    setShowModal(true)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function handleSave(e: FormEvent) {
    e.preventDefault()
    if (!formData.name.trim() || !formData.description.trim()) {
      showToast('error', 'Name and description are required')
      return
    }

    setSaving(true)
    try {
      if (editingPreset) {
        await client.updateTonePreset(editingPreset.id, formData)
        showToast('success', 'Tone preset updated successfully')
      } else {
        await client.createTonePreset(formData)
        showToast('success', 'Tone preset created successfully')
      }
      setShowModal(false)
      await loadPresets()
    } catch (error: unknown) {
      console.error('Failed to save:', error)
      const errorMessage = error instanceof Error ? error.message : 'Failed to save tone preset'
      showToast('error', errorMessage)
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete() {
    if (!deleteConfirm) return

    try {
      await client.deleteTonePreset(deleteConfirm.id)
      showToast('success', 'Tone preset deleted successfully')
      setDeleteConfirm(null)
      await loadPresets()
    } catch (error: unknown) {
      console.error('Failed to delete:', error)
      const errorMessage = error instanceof Error ? error.message : 'Failed to delete tone preset'
      showToast('error', errorMessage)
    }
  }

  return (
    <div className="glass-card rounded-xl p-6">
      {/* Header with Search and Create Button */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center space-x-3 flex-1 max-w-md">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && loadPresets()}
            placeholder="Search by name or description..."
            className="flex-1 px-4 py-2 bg-tsushin-dark/50 border border-tsushin-border rounded-lg text-white placeholder-tsushin-slate focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
          />
          <button
            onClick={loadPresets}
            className="px-4 py-2 bg-teal-500/20 text-teal-400 rounded-lg hover:bg-teal-500/30 transition-colors"
          >
            Search
          </button>
        </div>
        {canWrite && (
          <button
            onClick={openCreateModal}
            className="ml-4 px-4 py-2 bg-teal-500 hover:bg-teal-600 text-white rounded-lg font-medium transition-colors"
          >
            + New Tone Preset
          </button>
        )}
      </div>

      {/* Table */}
      {loading ? (
        <div className="text-center py-8 text-tsushin-slate">
          Loading tone presets...
        </div>
      ) : presets.length === 0 ? (
        <div className="text-center py-8 text-tsushin-slate">
          No tone presets found
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-tsushin-border">
                <th className="text-left py-3 px-4 text-sm font-medium text-white">Name</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-white">Description</th>
                <th className="text-center py-3 px-4 text-sm font-medium text-white">Usage</th>
                <th className="text-center py-3 px-4 text-sm font-medium text-white">Type</th>
                {canWrite && <th className="text-right py-3 px-4 text-sm font-medium text-white">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {presets.map((preset) => (
                <tr key={preset.id} className="border-b border-tsushin-border/50 hover:bg-tsushin-dark/30">
                  <td className="py-3 px-4 text-sm text-white font-medium">
                    {preset.name}
                  </td>
                  <td className="py-3 px-4 text-sm text-tsushin-slate max-w-md truncate">
                    {preset.description}
                  </td>
                  <td className="py-3 px-4 text-sm text-center text-tsushin-slate">
                    {preset.usage_count || 0} agents
                  </td>
                  <td className="py-3 px-4 text-center">
                    {preset.is_system ? (
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
                      {!preset.is_system && (
                        <button
                          onClick={() => openEditModal(preset)}
                          className="text-teal-400 hover:text-teal-300 text-sm font-medium transition-colors"
                        >
                          Edit
                        </button>
                      )}
                      <button
                        onClick={() => setDeleteConfirm({ id: preset.id, name: preset.name })}
                        disabled={preset.is_system}
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setShowModal(false)}>
          <div className="glass-card rounded-xl p-6 max-w-lg w-full mx-4" onClick={e => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-white mb-4">
              {editingPreset ? 'Edit Tone Preset' : 'Create Tone Preset'}
            </h3>
            <form onSubmit={handleSave} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-white mb-2">Name</label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  maxLength={50}
                  required
                  className="w-full px-4 py-2 bg-tsushin-deep border border-tsushin-border rounded-lg text-white placeholder-tsushin-slate focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
                  placeholder="e.g., Professional, Friendly, Casual"
                />
                <p className="text-xs text-tsushin-slate mt-1">{formData.name.length}/50 characters</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-white mb-2">Description</label>
                <textarea
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  required
                  rows={4}
                  className="w-full px-4 py-2 bg-tsushin-deep border border-tsushin-border rounded-lg text-white placeholder-tsushin-slate focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
                  placeholder="Describe the tone characteristics..."
                />
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
                  disabled={saving}
                  className="px-6 py-2 bg-teal-500 hover:bg-teal-600 text-white rounded-lg font-medium transition-colors disabled:opacity-50"
                >
                  {saving ? 'Saving...' : (editingPreset ? 'Update' : 'Create')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirmation */}
      <ConfirmDialog
        isOpen={!!deleteConfirm}
        title="Delete Tone Preset"
        message={`Are you sure you want to delete "${deleteConfirm?.name}"? This action cannot be undone.`}
        onConfirm={handleDelete}
        onCancel={() => setDeleteConfirm(null)}
      />
    </div>
  )
}
