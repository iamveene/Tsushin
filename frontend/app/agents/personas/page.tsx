'use client'

/**
 * Studio - Personas Management Page
 * Create and manage reusable personas
 */

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { api, Persona, TonePreset } from '@/lib/client'

interface PersonaFormData {
  name: string
  description: string
  role: string
  role_description: string
  tone_preset_id: number | null
  custom_tone: string
  personality_traits: string
  enabled_skills: number[]
  enabled_custom_tools: number[]
  enabled_knowledge_bases: number[]
  guardrails: string
  is_active: boolean
}

export default function PersonasPage() {
  const pathname = usePathname()
  const [personas, setPersonas] = useState<Persona[]>([])
  const [tonePresets, setTonePresets] = useState<TonePreset[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [editingPersona, setEditingPersona] = useState<Persona | null>(null)
  const [saving, setSaving] = useState(false)
  const [useCustomTone, setUseCustomTone] = useState(false)

  const [formData, setFormData] = useState<PersonaFormData>({
    name: '',
    description: '',
    role: '',
    role_description: '',
    tone_preset_id: null,
    custom_tone: '',
    personality_traits: '',
    enabled_skills: [],
    enabled_custom_tools: [],
    enabled_knowledge_bases: [],
    guardrails: '',
    is_active: true
  })

  useEffect(() => {
    loadData()
  }, [])

  useEffect(() => {
    const handleRefresh = () => {
      loadData()
    }
    window.addEventListener('tsushin:refresh', handleRefresh)
    return () => window.removeEventListener('tsushin:refresh', handleRefresh)
  }, [])

  const resetForm = () => {
    setFormData({
      name: '',
      description: '',
      role: '',
      role_description: '',
      tone_preset_id: null,
      custom_tone: '',
      personality_traits: '',
      enabled_skills: [],
      enabled_custom_tools: [],
      enabled_knowledge_bases: [],
      guardrails: '',
      is_active: true
    })
    setUseCustomTone(false)
    setEditingPersona(null)
  }

  const loadData = async () => {
    try {
      const [personasData, tonesData] = await Promise.all([
        api.getPersonas(),
        api.getTonePresets()
      ])
      setPersonas(personasData)
      setTonePresets(tonesData)
    } catch (err) {
      console.error('Failed to load personas:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleOpenCreateModal = () => {
    resetForm()
    setShowCreateModal(true)
  }

  const handleOpenEditModal = (persona: Persona) => {
    setEditingPersona(persona)
    setFormData({
      name: persona.name,
      description: persona.description,
      role: persona.role || '',
      role_description: persona.role_description || '',
      tone_preset_id: persona.tone_preset_id || null,
      custom_tone: persona.custom_tone || '',
      personality_traits: persona.personality_traits || '',
      enabled_skills: persona.enabled_skills || [],
      enabled_custom_tools: persona.enabled_custom_tools || [],
      enabled_knowledge_bases: persona.enabled_knowledge_bases || [],
      guardrails: persona.guardrails || '',
      is_active: persona.is_active
    })
    setUseCustomTone(!!persona.custom_tone)
    setShowCreateModal(true)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!formData.name.trim() || !formData.description.trim()) {
      alert('Name and description are required')
      return
    }

    setSaving(true)
    try {
      const payload: any = {
        name: formData.name,
        description: formData.description,
        role: formData.role,
        role_description: formData.role_description,
        personality_traits: formData.personality_traits,
        enabled_skills: formData.enabled_skills,
        enabled_custom_tools: formData.enabled_custom_tools,
        enabled_knowledge_bases: formData.enabled_knowledge_bases,
        guardrails: formData.guardrails,
        is_active: formData.is_active
      }

      if (useCustomTone) {
        payload.custom_tone = formData.custom_tone
        payload.tone_preset_id = null
      } else {
        payload.tone_preset_id = formData.tone_preset_id
        payload.custom_tone = null
      }

      if (editingPersona) {
        await api.updatePersona(editingPersona.id, payload)
      } else {
        await api.createPersona(payload)
      }

      setShowCreateModal(false)
      resetForm()
      await loadData()
    } catch (err: any) {
      alert(err.message || `Failed to ${editingPersona ? 'update' : 'create'} persona`)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(`Are you sure you want to delete "${name}"?`)) return

    try {
      await api.deletePersona(id)
      await loadData()
    } catch (err: any) {
      alert(err.message || 'Failed to delete persona')
    }
  }

  const handleClonePersona = (persona: Persona) => {
    setFormData({
      name: `${persona.name} (Copy)`,
      description: persona.description,
      role: persona.role || '',
      role_description: persona.role_description || '',
      tone_preset_id: persona.tone_preset_id || null,
      custom_tone: persona.custom_tone || '',
      personality_traits: persona.personality_traits || '',
      enabled_skills: persona.enabled_skills || [],
      enabled_custom_tools: persona.enabled_custom_tools || [],
      enabled_knowledge_bases: persona.enabled_knowledge_bases || [],
      guardrails: persona.guardrails || '',
      is_active: true
    })
    setUseCustomTone(!!persona.custom_tone)
    setEditingPersona(null)
    setShowCreateModal(true)
  }

  const systemPersonas = personas.filter(p => p.is_system)
  const customPersonas = personas.filter(p => !p.is_system)

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-lg text-gray-600 dark:text-gray-400">Loading personas...</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      {/* Header */}
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8 flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold text-white mb-2">Agent Studio</h1>
            <p className="text-tsushin-slate">Create and manage reusable personas for your agents</p>
          </div>
          <button
            onClick={handleOpenCreateModal}
            className="px-4 py-2 bg-tsushin-indigo text-white rounded-lg hover:bg-tsushin-indigo/90 transition-colors font-medium"
          >
            + Create Persona
          </button>
        </div>
      </div>

      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-0 space-y-6">
        {/* Sub Navigation */}
        <div className="bg-gray-900/50 border border-gray-800 rounded-lg shadow">
          <div className="border-b border-gray-800">
            <nav className="flex">
              <Link
                href="/agents"
                className={`px-6 py-3 font-medium text-sm border-b-2 transition-colors ${
                  pathname === '/agents'
                    ? 'border-tsushin-indigo text-tsushin-indigo'
                    : 'border-transparent text-tsushin-slate hover:text-white'
                }`}
              >
                Agents
              </Link>
              <Link
                href="/agents/contacts"
                className={`px-6 py-3 font-medium text-sm border-b-2 transition-colors ${
                  pathname === '/agents/contacts'
                    ? 'border-tsushin-indigo text-tsushin-indigo'
                    : 'border-transparent text-tsushin-slate hover:text-white'
                }`}
              >
                Contacts
              </Link>
              <Link
                href="/agents/personas"
                className={`px-6 py-3 font-medium text-sm border-b-2 transition-colors ${
                  pathname === '/agents/personas'
                    ? 'border-tsushin-indigo text-tsushin-indigo'
                    : 'border-transparent text-tsushin-slate hover:text-white'
                }`}
              >
                Personas
              </Link>
              <Link
                href="/agents/projects"
                className={`px-6 py-3 font-medium text-sm border-b-2 transition-colors ${
                  pathname?.startsWith('/agents/projects')
                    ? 'border-tsushin-indigo text-tsushin-indigo'
                    : 'border-transparent text-tsushin-slate hover:text-white'
                }`}
              >
                Projects
              </Link>
            </nav>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-gray-900/50 border border-gray-800 rounded-lg shadow p-5 border-l-4 border-l-tsushin-indigo">
            <p className="text-sm font-medium text-tsushin-slate">Total Personas</p>
            <p className="text-2xl font-bold text-white mt-1">{personas.length}</p>
          </div>
          <div className="bg-gray-900/50 border border-gray-800 rounded-lg shadow p-5 border-l-4 border-l-purple-500">
            <p className="text-sm font-medium text-tsushin-slate">System Templates</p>
            <p className="text-2xl font-bold text-white mt-1">{systemPersonas.length}</p>
          </div>
          <div className="bg-gray-900/50 border border-gray-800 rounded-lg shadow p-5 border-l-4 border-l-green-500">
            <p className="text-sm font-medium text-tsushin-slate">Custom Personas</p>
            <p className="text-2xl font-bold text-white mt-1">{customPersonas.length}</p>
          </div>
        </div>

        {/* System Persona Templates */}
        <div className="bg-gray-900/50 border border-gray-800 rounded-lg shadow">
          <div className="px-6 py-4 border-b border-gray-800">
            <h3 className="text-lg font-semibold text-white">Persona Template Library</h3>
            <p className="text-sm text-tsushin-slate mt-1">Pre-built persona templates from Tsushin. Clone to customize.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 p-6">
            {systemPersonas.map((persona) => (
              <div
                key={persona.id}
                className="bg-gray-800/50 border border-gray-700 rounded-lg p-4 hover:border-tsushin-indigo/50 transition-colors"
              >
                <div className="mb-3">
                  <h4 className="font-semibold text-white">{persona.name}</h4>
                  <p className="text-xs text-tsushin-slate mt-1">{persona.description}</p>
                </div>

                <div className="space-y-2 text-sm">
                  {persona.role && (
                    <div className="flex items-start gap-2">
                      <span className="text-tsushin-slate">Role:</span>
                      <span className="text-white font-medium">{persona.role}</span>
                    </div>
                  )}
                  {persona.tone_preset_name && (
                    <div className="flex items-start gap-2">
                      <span className="text-tsushin-slate">Tone:</span>
                      <span className="text-white">{persona.tone_preset_name}</span>
                    </div>
                  )}
                  {persona.personality_traits && (
                    <div className="flex items-start gap-2">
                      <span className="text-tsushin-slate">Traits:</span>
                      <span className="text-white">{persona.personality_traits}</span>
                    </div>
                  )}
                </div>

                <div className="mt-4 pt-3 border-t border-gray-700">
                  <button
                    onClick={() => handleClonePersona(persona)}
                    className="w-full px-3 py-1.5 text-sm bg-tsushin-indigo/10 text-tsushin-indigo border border-tsushin-indigo/20 rounded-md hover:bg-tsushin-indigo/20"
                  >
                    Clone Template
                  </button>
                </div>
              </div>
            ))}
            {systemPersonas.length === 0 && (
              <div className="col-span-2 text-center py-8 text-tsushin-slate">
                No system templates available
              </div>
            )}
          </div>
        </div>

        {/* Custom Personas */}
        <div className="bg-gray-900/50 border border-gray-800 rounded-lg shadow">
          <div className="px-6 py-4 border-b border-gray-800">
            <h3 className="text-lg font-semibold text-white">Custom Personas</h3>
            <p className="text-sm text-tsushin-slate mt-1">Your custom personas that can be assigned to agents</p>
          </div>
          {customPersonas.length === 0 ? (
            <div className="px-6 py-12 text-center">
              <p className="text-tsushin-slate mb-4">No custom personas created yet</p>
              <button
                onClick={handleOpenCreateModal}
                className="px-4 py-2 bg-tsushin-indigo text-white rounded-lg hover:bg-tsushin-indigo/90"
              >
                Create Your First Persona
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 p-6">
              {customPersonas.map((persona) => (
                <div
                  key={persona.id}
                  className="bg-gray-800/50 border border-gray-700 rounded-lg p-4 hover:border-tsushin-indigo/50 transition-colors"
                >
                  <div className="mb-3">
                    <div className="flex items-center gap-2">
                      <h4 className="font-semibold text-white">{persona.name}</h4>
                      {!persona.is_active && (
                        <span className="px-2 py-0.5 text-xs bg-gray-500/10 text-gray-400 rounded-full">
                          Inactive
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-tsushin-slate mt-1">{persona.description}</p>
                    {persona.ai_summary && (
                      <div className="mt-2 p-2 bg-tsushin-indigo/10 border border-tsushin-indigo/20 rounded-md">
                        <p className="text-xs text-tsushin-indigo italic">AI Summary: {persona.ai_summary}</p>
                      </div>
                    )}
                  </div>

                  <div className="space-y-2 text-sm">
                    {persona.role && (
                      <div className="flex items-start gap-2">
                        <span className="text-tsushin-slate">Role:</span>
                        <span className="text-white font-medium">{persona.role}</span>
                      </div>
                    )}
                    {persona.tone_preset_name && (
                      <div className="flex items-start gap-2">
                        <span className="text-tsushin-slate">Tone:</span>
                        <span className="text-white">{persona.tone_preset_name}</span>
                      </div>
                    )}
                    {persona.custom_tone && (
                      <div className="flex items-start gap-2">
                        <span className="text-tsushin-slate">Custom Tone:</span>
                        <span className="text-white text-xs">{persona.custom_tone}</span>
                      </div>
                    )}
                    {persona.personality_traits && (
                      <div className="flex items-start gap-2">
                        <span className="text-tsushin-slate">Traits:</span>
                        <span className="text-white">{persona.personality_traits}</span>
                      </div>
                    )}
                    {persona.guardrails && (
                      <div className="flex items-start gap-2">
                        <span className="text-tsushin-slate">Guardrails:</span>
                        <span className="text-white text-xs italic">{persona.guardrails.substring(0, 80)}{persona.guardrails.length > 80 ? '...' : ''}</span>
                      </div>
                    )}
                  </div>

                  <div className="mt-4 pt-3 border-t border-gray-700 flex gap-2">
                    <button
                      onClick={() => handleOpenEditModal(persona)}
                      className="px-3 py-1.5 text-sm bg-tsushin-indigo/10 text-tsushin-indigo border border-tsushin-indigo/20 rounded-md hover:bg-tsushin-indigo/20 flex-1"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => handleClonePersona(persona)}
                      className="px-3 py-1.5 text-sm bg-gray-700 text-gray-300 rounded-md hover:bg-gray-600"
                    >
                      Clone
                    </button>
                    <button
                      onClick={() => handleDelete(persona.id, persona.name)}
                      className="px-3 py-1.5 text-sm bg-red-500/10 text-red-400 border border-red-500/20 rounded-md hover:bg-red-500/20"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Create/Edit Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <h2 className="text-xl font-bold text-white mb-4">
              {editingPersona ? 'Edit Persona' : 'Create New Persona'}
            </h2>

            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Name */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Name *
                </label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-600 rounded-lg focus:ring-2 focus:ring-tsushin-indigo bg-gray-900 text-white"
                  required
                  placeholder="e.g., Friendly Assistant, Professional Expert"
                  disabled={editingPersona?.is_system}
                />
              </div>

              {/* Description */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Description *
                </label>
                <textarea
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-600 rounded-lg focus:ring-2 focus:ring-tsushin-indigo h-20 bg-gray-900 text-white"
                  required
                  placeholder="Describe the persona's role and characteristics"
                />
              </div>

              {/* Role */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Role
                </label>
                <input
                  type="text"
                  value={formData.role}
                  onChange={(e) => setFormData({ ...formData, role: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-600 rounded-lg focus:ring-2 focus:ring-tsushin-indigo bg-gray-900 text-white"
                  placeholder="e.g., Customer Support Specialist, Technical Expert"
                />
              </div>

              {/* Role Description */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Role Description
                </label>
                <textarea
                  value={formData.role_description}
                  onChange={(e) => setFormData({ ...formData, role_description: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-600 rounded-lg focus:ring-2 focus:ring-tsushin-indigo h-20 bg-gray-900 text-white"
                  placeholder="Detailed role expectations and responsibilities"
                />
              </div>

              {/* Personality Traits */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Personality Traits
                </label>
                <input
                  type="text"
                  value={formData.personality_traits}
                  onChange={(e) => setFormData({ ...formData, personality_traits: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-600 rounded-lg focus:ring-2 focus:ring-tsushin-indigo bg-gray-900 text-white"
                  placeholder="e.g., Empathetic, patient, enthusiastic, supportive"
                />
              </div>

              {/* Tone Configuration */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Tone Configuration
                </label>
                <div className="space-y-3">
                  <div className="flex items-center gap-4">
                    <label className="flex items-center text-gray-300">
                      <input
                        type="radio"
                        checked={!useCustomTone}
                        onChange={() => setUseCustomTone(false)}
                        className="mr-2"
                      />
                      Use Tone Preset
                    </label>
                    <label className="flex items-center text-gray-300">
                      <input
                        type="radio"
                        checked={useCustomTone}
                        onChange={() => setUseCustomTone(true)}
                        className="mr-2"
                      />
                      Custom Tone
                    </label>
                  </div>

                  {!useCustomTone ? (
                    <select
                      value={formData.tone_preset_id || ''}
                      onChange={(e) => setFormData({ ...formData, tone_preset_id: Number(e.target.value) || null })}
                      className="w-full px-3 py-2 border border-gray-600 rounded-lg focus:ring-2 focus:ring-tsushin-indigo bg-gray-900 text-white"
                    >
                      <option value="">Select a tone preset...</option>
                      {tonePresets.map(t => (
                        <option key={t.id} value={t.id}>{t.name} - {t.description.substring(0, 50)}...</option>
                      ))}
                    </select>
                  ) : (
                    <textarea
                      value={formData.custom_tone}
                      onChange={(e) => setFormData({ ...formData, custom_tone: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-600 rounded-lg focus:ring-2 focus:ring-tsushin-indigo h-24 bg-gray-900 text-white"
                      placeholder="Describe the tone and communication style"
                    />
                  )}
                </div>
              </div>

              {/* Guardrails */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Guardrails & Safety Rules
                </label>
                <textarea
                  value={formData.guardrails}
                  onChange={(e) => setFormData({ ...formData, guardrails: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-600 rounded-lg focus:ring-2 focus:ring-tsushin-indigo h-24 bg-gray-900 text-white"
                  placeholder="Safety rules and constraints"
                />
              </div>

              {/* Active Toggle */}
              <div className="flex items-center">
                <input
                  type="checkbox"
                  id="is_active"
                  checked={formData.is_active}
                  onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                  className="mr-2"
                />
                <label htmlFor="is_active" className="text-sm font-medium text-gray-300">
                  Active
                </label>
              </div>

              {/* Actions */}
              <div className="flex justify-end gap-3 pt-4 border-t border-gray-700">
                <button
                  type="button"
                  onClick={() => {
                    setShowCreateModal(false)
                    resetForm()
                  }}
                  className="px-4 py-2 border border-gray-600 rounded-lg hover:bg-gray-700 text-white"
                  disabled={saving}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-tsushin-indigo text-white rounded-lg hover:bg-tsushin-indigo/90 disabled:opacity-50"
                  disabled={saving}
                >
                  {saving ? 'Saving...' : editingPersona ? 'Update Persona' : 'Create Persona'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
