'use client'

/**
 * Custom Skills Management Page (Phase 22/23)
 * Studio > Custom Skills
 *
 * List, create, edit, delete, deploy, scan, and test tenant-authored custom skills.
 * Supports instruction-based and script-based skill types.
 */

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { useAuth } from '@/contexts/AuthContext'
import { api, CustomSkill, CustomSkillCreate, CustomSkillUpdate } from '@/lib/client'

// ==================== Helpers ====================

function scanBadge(status: string) {
  switch (status) {
    case 'clean':
      return 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
    case 'pending':
      return 'bg-amber-500/15 text-amber-300 border border-amber-500/30'
    case 'rejected':
      return 'bg-red-500/15 text-red-300 border border-red-500/30'
    default:
      return 'bg-white/5 text-tsushin-slate border border-white/10'
  }
}

function typeBadge(variant: string) {
  switch (variant) {
    case 'instruction':
      return 'bg-blue-500/15 text-blue-300 border border-blue-500/30'
    case 'script':
      return 'bg-violet-500/15 text-violet-300 border border-violet-500/30'
    case 'mcp_server':
      return 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/30'
    default:
      return 'bg-white/5 text-tsushin-slate border border-white/10'
  }
}

function typeLabel(variant: string): string {
  switch (variant) {
    case 'instruction': return 'Instruction'
    case 'script': return 'Script'
    case 'mcp_server': return 'MCP Server'
    default: return variant
  }
}

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '--'
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

// ==================== Page ====================

export default function CustomSkillsPage() {
  const { hasPermission } = useAuth()
  const canCreate = hasPermission('skills.custom.create')
  const canDelete = hasPermission('skills.custom.delete')
  const canExecute = hasPermission('skills.custom.execute')

  const [skills, setSkills] = useState<CustomSkill[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Create/Edit modal
  const [showModal, setShowModal] = useState(false)
  const [editingSkill, setEditingSkill] = useState<CustomSkill | null>(null)
  const [saving, setSaving] = useState(false)

  // Form state
  const [formName, setFormName] = useState('')
  const [formDescription, setFormDescription] = useState('')
  const [formIcon, setFormIcon] = useState('')
  const [formType, setFormType] = useState<string>('instruction')
  const [formExecMode, setFormExecMode] = useState<string>('tool')
  const [formTriggerMode, setFormTriggerMode] = useState<string>('llm_decided')
  const [formInstructions, setFormInstructions] = useState('')
  const [formScriptContent, setFormScriptContent] = useState('')
  const [formScriptEntrypoint, setFormScriptEntrypoint] = useState('')
  const [formScriptLanguage, setFormScriptLanguage] = useState<string>('python')
  const [formTimeout, setFormTimeout] = useState(30)
  const [formPriority, setFormPriority] = useState(50)

  // Delete confirm
  const [deletingSkill, setDeletingSkill] = useState<CustomSkill | null>(null)

  // Action states
  const [deployingId, setDeployingId] = useState<number | null>(null)
  const [scanningId, setScanningId] = useState<number | null>(null)
  const [togglingId, setTogglingId] = useState<number | null>(null)

  // Test modal
  const [testingSkill, setTestingSkill] = useState<CustomSkill | null>(null)
  const [testArgs, setTestArgs] = useState('{}')
  const [testRunning, setTestRunning] = useState(false)
  const [testResult, setTestResult] = useState<any>(null)

  // Fetch skills
  const fetchSkills = useCallback(async () => {
    try {
      setError(null)
      const data = await api.listCustomSkills()
      setSkills(data)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchSkills()
  }, [fetchSkills])

  // Auto-dismiss success messages
  useEffect(() => {
    if (success) {
      const t = setTimeout(() => setSuccess(null), 4000)
      return () => clearTimeout(t)
    }
  }, [success])

  // Open create modal
  const openCreate = () => {
    setEditingSkill(null)
    setFormName('')
    setFormDescription('')
    setFormIcon('')
    setFormType('instruction')
    setFormExecMode('tool')
    setFormTriggerMode('llm_decided')
    setFormInstructions('')
    setFormScriptContent('')
    setFormScriptEntrypoint('main.py')
    setFormScriptLanguage('python')
    setFormTimeout(30)
    setFormPriority(50)
    setShowModal(true)
  }

  // Open edit modal
  const openEdit = (skill: CustomSkill) => {
    setEditingSkill(skill)
    setFormName(skill.name)
    setFormDescription(skill.description || '')
    setFormIcon(skill.icon || '')
    setFormType(skill.skill_type_variant)
    setFormExecMode(skill.execution_mode)
    setFormTriggerMode(skill.trigger_mode)
    setFormInstructions(skill.instructions_md || '')
    setFormScriptContent(skill.script_content || '')
    setFormScriptEntrypoint(skill.script_entrypoint || 'main.py')
    setFormScriptLanguage(skill.script_language || 'python')
    setFormTimeout(skill.timeout_seconds)
    setFormPriority(skill.priority)
    setShowModal(true)
  }

  // Save (create or update)
  const handleSave = async () => {
    if (!formName.trim()) {
      setError('Skill name is required')
      return
    }

    setSaving(true)
    setError(null)

    try {
      if (editingSkill) {
        const update: CustomSkillUpdate = {
          name: formName,
          description: formDescription || undefined,
          icon: formIcon || undefined,
          skill_type_variant: formType,
          execution_mode: formExecMode,
          trigger_mode: formTriggerMode,
          instructions_md: formType === 'instruction' ? formInstructions : undefined,
          script_content: formType === 'script' ? formScriptContent : undefined,
          script_entrypoint: formType === 'script' ? formScriptEntrypoint : undefined,
          script_language: formType === 'script' ? formScriptLanguage : undefined,
          timeout_seconds: formTimeout,
          priority: formPriority,
        }
        await api.updateCustomSkill(editingSkill.id, update)
        setSuccess(`Skill "${formName}" updated`)
      } else {
        const create: CustomSkillCreate = {
          name: formName,
          description: formDescription || undefined,
          icon: formIcon || undefined,
          skill_type_variant: formType,
          execution_mode: formExecMode,
          trigger_mode: formTriggerMode,
          instructions_md: formType === 'instruction' ? formInstructions : undefined,
          script_content: formType === 'script' ? formScriptContent : undefined,
          script_entrypoint: formType === 'script' ? formScriptEntrypoint : undefined,
          script_language: formType === 'script' ? formScriptLanguage : undefined,
          timeout_seconds: formTimeout,
          priority: formPriority,
        }
        await api.createCustomSkill(create)
        setSuccess(`Skill "${formName}" created`)
      }
      setShowModal(false)
      fetchSkills()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  // Delete
  const handleDelete = async () => {
    if (!deletingSkill) return
    try {
      await api.deleteCustomSkill(deletingSkill.id)
      setSuccess(`Skill "${deletingSkill.name}" deleted`)
      setDeletingSkill(null)
      fetchSkills()
    } catch (e: any) {
      setError(e.message)
    }
  }

  // Toggle enable/disable
  const handleToggle = async (skill: CustomSkill) => {
    setTogglingId(skill.id)
    try {
      await api.updateCustomSkill(skill.id, { is_enabled: !skill.is_enabled })
      fetchSkills()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setTogglingId(null)
    }
  }

  // Deploy
  const handleDeploy = async (skill: CustomSkill) => {
    setDeployingId(skill.id)
    try {
      await api.deployCustomSkill(skill.id)
      setSuccess(`Skill "${skill.name}" deployed to container`)
      fetchSkills()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setDeployingId(null)
    }
  }

  // Scan
  const handleScan = async (skill: CustomSkill) => {
    setScanningId(skill.id)
    try {
      const result = await api.scanCustomSkill(skill.id)
      if (result.scan_status === 'rejected') {
        setError(`Scan flagged skill "${skill.name}" as potentially unsafe`)
      } else {
        setSuccess(`Skill "${skill.name}" passed security scan`)
      }
      fetchSkills()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setScanningId(null)
    }
  }

  // Test
  const handleTest = async () => {
    if (!testingSkill) return
    setTestRunning(true)
    setTestResult(null)
    try {
      let args = {}
      try { args = JSON.parse(testArgs) } catch { /* use empty */ }
      const result = await api.testCustomSkill(testingSkill.id, { arguments: args })
      setTestResult(result)
    } catch (e: any) {
      setTestResult({ success: false, output: e.message, execution_time_ms: 0 })
    } finally {
      setTestRunning(false)
    }
  }

  // Stats
  const totalSkills = skills.length
  const activeSkills = skills.filter(s => s.is_enabled).length
  const instructionSkills = skills.filter(s => s.skill_type_variant === 'instruction').length
  const scriptSkills = skills.filter(s => s.skill_type_variant === 'script').length

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="max-w-6xl mx-auto">
          <div className="animate-pulse space-y-4">
            <div className="h-8 bg-white/5 rounded w-48" />
            <div className="grid grid-cols-4 gap-4">
              {[1,2,3,4].map(i => <div key={i} className="h-20 bg-white/5 rounded-xl" />)}
            </div>
            <div className="h-64 bg-white/5 rounded-xl" />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-6xl mx-auto">
        {/* Breadcrumb */}
        <div className="mb-6">
          <Link href="/agents" className="text-tsushin-slate hover:text-white transition-colors text-sm">
            Studio
          </Link>
          <span className="text-tsushin-slate/50 mx-2">/</span>
          <span className="text-white text-sm">Custom Skills</span>
        </div>

        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-display font-bold text-white">Custom Skills</h1>
            <p className="text-tsushin-slate mt-1">
              Create and manage tenant-authored skills for your agents
            </p>
          </div>
          {canCreate && (
            <button
              onClick={openCreate}
              className="px-4 py-2 bg-tsushin-indigo hover:bg-tsushin-indigo/80 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              New Skill
            </button>
          )}
        </div>

        {/* Alerts */}
        {error && (
          <div className="mb-6 p-4 bg-red-500/10 border border-red-500/30 rounded-xl text-red-300 flex items-start gap-3">
            <svg className="w-5 h-5 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
            <span>{error}</span>
            <button onClick={() => setError(null)} className="ml-auto text-red-400 hover:text-red-300">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>
        )}
        {success && (
          <div className="mb-6 p-4 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-emerald-300 flex items-center gap-3">
            <svg className="w-5 h-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <span>{success}</span>
          </div>
        )}

        {/* Stat Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <div className="bg-tsushin-surface border border-white/10 rounded-xl p-4">
            <p className="text-tsushin-slate text-xs uppercase tracking-wider mb-1">Total</p>
            <p className="text-2xl font-bold text-white">{totalSkills}</p>
          </div>
          <div className="bg-tsushin-surface border border-white/10 rounded-xl p-4">
            <p className="text-tsushin-slate text-xs uppercase tracking-wider mb-1">Active</p>
            <p className="text-2xl font-bold text-emerald-400">{activeSkills}</p>
          </div>
          <div className="bg-tsushin-surface border border-white/10 rounded-xl p-4">
            <p className="text-tsushin-slate text-xs uppercase tracking-wider mb-1">Instruction</p>
            <p className="text-2xl font-bold text-blue-400">{instructionSkills}</p>
          </div>
          <div className="bg-tsushin-surface border border-white/10 rounded-xl p-4">
            <p className="text-tsushin-slate text-xs uppercase tracking-wider mb-1">Script</p>
            <p className="text-2xl font-bold text-violet-400">{scriptSkills}</p>
          </div>
        </div>

        {/* Skills List */}
        {skills.length === 0 ? (
          <div className="bg-tsushin-surface border border-white/10 rounded-xl p-12 text-center">
            <div className="w-16 h-16 mx-auto mb-4 rounded-xl bg-white/5 flex items-center justify-center">
              <svg className="w-8 h-8 text-tsushin-slate" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
              </svg>
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">No custom skills yet</h3>
            <p className="text-tsushin-slate mb-6 max-w-md mx-auto">
              Create your first custom skill to extend your agents with instruction-based prompts or executable scripts.
            </p>
            {canCreate && (
              <button
                onClick={openCreate}
                className="px-4 py-2 bg-tsushin-indigo hover:bg-tsushin-indigo/80 text-white rounded-lg font-medium transition-colors"
              >
                Create First Skill
              </button>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            {skills.map((skill) => (
              <div
                key={skill.id}
                className="bg-tsushin-surface border border-white/10 rounded-xl p-5 hover:border-white/20 transition-colors"
              >
                <div className="flex items-start justify-between gap-4">
                  {/* Left: Icon + Info */}
                  <div className="flex items-start gap-4 min-w-0 flex-1">
                    <div className="w-10 h-10 rounded-lg bg-white/5 flex items-center justify-center shrink-0 text-lg">
                      {skill.icon || (skill.skill_type_variant === 'script' ? '\u2699' : '\u2728')}
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <h3 className="font-semibold text-white truncate">{skill.name}</h3>
                        <span className={`text-xs px-2 py-0.5 rounded-full ${typeBadge(skill.skill_type_variant)}`}>
                          {typeLabel(skill.skill_type_variant)}
                        </span>
                        <span className={`text-xs px-2 py-0.5 rounded-full ${scanBadge(skill.scan_status)}`}>
                          {skill.scan_status}
                        </span>
                        {!skill.is_enabled && (
                          <span className="text-xs px-2 py-0.5 rounded-full bg-white/5 text-tsushin-slate border border-white/10">
                            disabled
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-tsushin-slate truncate">
                        {skill.description || 'No description'}
                      </p>
                      <p className="text-xs text-tsushin-slate/60 mt-1">
                        v{skill.version} &middot; {skill.execution_mode} &middot; {skill.trigger_mode} &middot; Updated {formatDate(skill.updated_at)}
                      </p>
                    </div>
                  </div>

                  {/* Right: Actions */}
                  <div className="flex items-center gap-2 shrink-0">
                    {/* Enable/Disable toggle */}
                    <button
                      onClick={() => handleToggle(skill)}
                      disabled={togglingId === skill.id}
                      className={`relative w-10 h-5 rounded-full transition-colors ${
                        skill.is_enabled ? 'bg-emerald-500' : 'bg-white/10'
                      }`}
                      title={skill.is_enabled ? 'Disable' : 'Enable'}
                    >
                      <span className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform ${
                        skill.is_enabled ? 'translate-x-5' : ''
                      }`} />
                    </button>

                    {/* Deploy (script only) */}
                    {skill.skill_type_variant === 'script' && canCreate && (
                      <button
                        onClick={() => handleDeploy(skill)}
                        disabled={deployingId === skill.id}
                        className="p-2 text-tsushin-slate hover:text-violet-300 transition-colors"
                        title="Deploy to container"
                      >
                        {deployingId === skill.id ? (
                          <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
                        ) : (
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                          </svg>
                        )}
                      </button>
                    )}

                    {/* Scan */}
                    {canCreate && (
                      <button
                        onClick={() => handleScan(skill)}
                        disabled={scanningId === skill.id}
                        className="p-2 text-tsushin-slate hover:text-amber-300 transition-colors"
                        title="Re-scan with Sentinel"
                      >
                        {scanningId === skill.id ? (
                          <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
                        ) : (
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                          </svg>
                        )}
                      </button>
                    )}

                    {/* Test */}
                    {canExecute && (
                      <button
                        onClick={() => { setTestingSkill(skill); setTestResult(null); setTestArgs('{}') }}
                        className="p-2 text-tsushin-slate hover:text-teal-300 transition-colors"
                        title="Test skill"
                      >
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                      </button>
                    )}

                    {/* Edit */}
                    {canCreate && (
                      <button
                        onClick={() => openEdit(skill)}
                        className="p-2 text-tsushin-slate hover:text-white transition-colors"
                        title="Edit"
                      >
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                        </svg>
                      </button>
                    )}

                    {/* Delete */}
                    {canDelete && (
                      <button
                        onClick={() => setDeletingSkill(skill)}
                        className="p-2 text-tsushin-slate hover:text-red-400 transition-colors"
                        title="Delete"
                      >
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* ==================== Create/Edit Modal ==================== */}
        {showModal && (
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-tsushin-surface border border-white/10 rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
              <div className="p-6 border-b border-white/10">
                <h2 className="text-xl font-display font-bold text-white">
                  {editingSkill ? 'Edit Skill' : 'New Custom Skill'}
                </h2>
              </div>
              <div className="p-6 space-y-5">
                {/* Name */}
                <div>
                  <label className="block text-sm font-medium text-tsushin-slate mb-1">Name *</label>
                  <input
                    type="text"
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-tsushin-slate/50 focus:outline-none focus:border-tsushin-accent/50"
                    placeholder="e.g. Customer Lookup"
                  />
                </div>

                {/* Description */}
                <div>
                  <label className="block text-sm font-medium text-tsushin-slate mb-1">Description</label>
                  <input
                    type="text"
                    value={formDescription}
                    onChange={(e) => setFormDescription(e.target.value)}
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-tsushin-slate/50 focus:outline-none focus:border-tsushin-accent/50"
                    placeholder="What does this skill do?"
                  />
                </div>

                {/* Icon */}
                <div>
                  <label className="block text-sm font-medium text-tsushin-slate mb-1">Icon (emoji)</label>
                  <input
                    type="text"
                    value={formIcon}
                    onChange={(e) => setFormIcon(e.target.value)}
                    className="w-20 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white text-center focus:outline-none focus:border-tsushin-accent/50"
                    placeholder=""
                    maxLength={4}
                  />
                </div>

                {/* Type row */}
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-tsushin-slate mb-1">Type</label>
                    <select
                      value={formType}
                      onChange={(e) => setFormType(e.target.value)}
                      className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-tsushin-accent/50"
                    >
                      <option value="instruction">Instruction</option>
                      <option value="script">Script</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-tsushin-slate mb-1">Execution Mode</label>
                    <select
                      value={formExecMode}
                      onChange={(e) => setFormExecMode(e.target.value)}
                      className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-tsushin-accent/50"
                    >
                      <option value="tool">Tool</option>
                      <option value="hybrid">Hybrid</option>
                      <option value="passive">Passive</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-tsushin-slate mb-1">Trigger Mode</label>
                    <select
                      value={formTriggerMode}
                      onChange={(e) => setFormTriggerMode(e.target.value)}
                      className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-tsushin-accent/50"
                    >
                      <option value="llm_decided">LLM Decided</option>
                      <option value="keyword">Keyword</option>
                      <option value="always_on">Always On</option>
                    </select>
                  </div>
                </div>

                {/* Instruction content */}
                {formType === 'instruction' && (
                  <div>
                    <label className="block text-sm font-medium text-tsushin-slate mb-1">
                      Instructions (Markdown)
                    </label>
                    <textarea
                      value={formInstructions}
                      onChange={(e) => setFormInstructions(e.target.value)}
                      rows={8}
                      className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white font-mono text-sm placeholder-tsushin-slate/50 focus:outline-none focus:border-tsushin-accent/50 resize-y"
                      placeholder="Enter skill instructions in Markdown..."
                    />
                    <p className="text-xs text-tsushin-slate/60 mt-1">
                      {formInstructions.length}/8000 characters
                    </p>
                  </div>
                )}

                {/* Script content */}
                {formType === 'script' && (
                  <>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-tsushin-slate mb-1">Language</label>
                        <select
                          value={formScriptLanguage}
                          onChange={(e) => setFormScriptLanguage(e.target.value)}
                          className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-tsushin-accent/50"
                        >
                          <option value="python">Python</option>
                          <option value="bash">Bash</option>
                          <option value="nodejs">Node.js</option>
                        </select>
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-tsushin-slate mb-1">Entrypoint</label>
                        <input
                          type="text"
                          value={formScriptEntrypoint}
                          onChange={(e) => setFormScriptEntrypoint(e.target.value)}
                          className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white font-mono text-sm placeholder-tsushin-slate/50 focus:outline-none focus:border-tsushin-accent/50"
                          placeholder="main.py"
                        />
                      </div>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-tsushin-slate mb-1">Script Content</label>
                      <textarea
                        value={formScriptContent}
                        onChange={(e) => setFormScriptContent(e.target.value)}
                        rows={12}
                        className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white font-mono text-sm placeholder-tsushin-slate/50 focus:outline-none focus:border-tsushin-accent/50 resize-y"
                        placeholder={formScriptLanguage === 'python' ? 'import os, json\n\ninput_data = json.loads(os.environ.get("TSUSHIN_INPUT", "{}"))\nprint(json.dumps({"output": "Hello from script!"}))' : '#!/bin/bash\necho \'{"output": "Hello from script!"}\''}
                      />
                      <p className="text-xs text-tsushin-slate/60 mt-1">
                        {new Blob([formScriptContent]).size.toLocaleString()}/262,144 bytes &middot; Output JSON to stdout with an "output" key
                      </p>
                    </div>
                  </>
                )}

                {/* Timeout & Priority */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-tsushin-slate mb-1">Timeout (seconds)</label>
                    <input
                      type="number"
                      value={formTimeout}
                      onChange={(e) => setFormTimeout(Math.max(1, Math.min(300, parseInt(e.target.value) || 30)))}
                      className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-tsushin-accent/50"
                      min={1}
                      max={300}
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-tsushin-slate mb-1">Priority (1-100)</label>
                    <input
                      type="number"
                      value={formPriority}
                      onChange={(e) => setFormPriority(Math.max(1, Math.min(100, parseInt(e.target.value) || 50)))}
                      className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-tsushin-accent/50"
                      min={1}
                      max={100}
                    />
                  </div>
                </div>
              </div>

              {/* Modal footer */}
              <div className="p-6 border-t border-white/10 flex justify-end gap-3">
                <button
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 text-tsushin-slate hover:text-white transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving || !formName.trim()}
                  className="px-5 py-2 bg-tsushin-indigo hover:bg-tsushin-indigo/80 disabled:opacity-50 text-white rounded-lg font-medium transition-colors"
                >
                  {saving ? 'Saving...' : (editingSkill ? 'Update' : 'Create')}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ==================== Delete Confirmation ==================== */}
        {deletingSkill && (
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-tsushin-surface border border-white/10 rounded-2xl w-full max-w-md p-6">
              <h3 className="text-lg font-bold text-white mb-2">Delete Skill</h3>
              <p className="text-tsushin-slate mb-6">
                Are you sure you want to delete <span className="text-white font-medium">"{deletingSkill.name}"</span>? This will also remove all execution history. This action cannot be undone.
              </p>
              <div className="flex justify-end gap-3">
                <button
                  onClick={() => setDeletingSkill(null)}
                  className="px-4 py-2 text-tsushin-slate hover:text-white transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleDelete}
                  className="px-4 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-300 rounded-lg font-medium transition-colors"
                >
                  Delete
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ==================== Test Modal ==================== */}
        {testingSkill && (
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-tsushin-surface border border-white/10 rounded-2xl w-full max-w-lg max-h-[80vh] overflow-y-auto">
              <div className="p-6 border-b border-white/10 flex items-center justify-between">
                <h2 className="text-lg font-display font-bold text-white">
                  Test: {testingSkill.name}
                </h2>
                <button onClick={() => setTestingSkill(null)} className="text-tsushin-slate hover:text-white">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
              </div>
              <div className="p-6 space-y-4">
                <div>
                  <label className="block text-sm font-medium text-tsushin-slate mb-1">Arguments (JSON)</label>
                  <textarea
                    value={testArgs}
                    onChange={(e) => setTestArgs(e.target.value)}
                    rows={4}
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white font-mono text-sm focus:outline-none focus:border-tsushin-accent/50"
                    placeholder='{"key": "value"}'
                  />
                </div>
                <button
                  onClick={handleTest}
                  disabled={testRunning}
                  className="w-full px-4 py-2 bg-tsushin-indigo hover:bg-tsushin-indigo/80 disabled:opacity-50 text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
                >
                  {testRunning ? (
                    <>
                      <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
                      Running...
                    </>
                  ) : (
                    'Run Test'
                  )}
                </button>

                {testResult && (
                  <div className={`rounded-lg border p-4 ${testResult.success ? 'bg-emerald-500/5 border-emerald-500/20' : 'bg-red-500/5 border-red-500/20'}`}>
                    <div className="flex items-center justify-between mb-2">
                      <span className={`text-sm font-medium ${testResult.success ? 'text-emerald-300' : 'text-red-300'}`}>
                        {testResult.success ? 'Success' : 'Failed'}
                      </span>
                      {testResult.execution_time_ms != null && (
                        <span className="text-xs text-tsushin-slate">{testResult.execution_time_ms}ms</span>
                      )}
                    </div>
                    <pre className="text-sm text-white/80 whitespace-pre-wrap font-mono break-all max-h-60 overflow-y-auto">
                      {testResult.output}
                    </pre>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
