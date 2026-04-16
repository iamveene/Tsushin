'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { api, CustomSkill } from '@/lib/client'
import { WrenchIcon } from '@/components/ui/icons'
import ToggleSwitch from '@/components/ui/ToggleSwitch'

interface Props {
  agentId: number
}

export default function AgentCustomSkillsManager({ agentId }: Props) {
  const [loading, setLoading] = useState(true)
  const [assignments, setAssignments] = useState<any[]>([])
  const [availableCustomSkills, setAvailableCustomSkills] = useState<CustomSkill[]>([])
  const [showPicker, setShowPicker] = useState(false)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [creating, setCreating] = useState(false)
  const [createForm, setCreateForm] = useState({ name: '', description: '', instructions_md: '' })

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [assigned, all] = await Promise.all([
        api.getAgentCustomSkills(agentId).catch(() => []),
        api.getCustomSkills().catch(() => [] as CustomSkill[]),
      ])
      setAssignments(assigned)
      setAvailableCustomSkills(all)
    } catch (err) {
      console.error('Failed to load custom skills:', err)
    } finally {
      setLoading(false)
    }
  }, [agentId])

  useEffect(() => {
    loadData()
  }, [loadData])

  const assignedIds = useMemo(
    () => new Set(assignments.map((a: any) => a.custom_skill_id ?? a.skill?.id).filter((v: any) => v != null)),
    [assignments]
  )

  const unassignedAvailable = useMemo(
    () => availableCustomSkills.filter((s) => !assignedIds.has(s.id)),
    [availableCustomSkills, assignedIds]
  )

  const handleToggle = async (assignment: any, checked: boolean) => {
    try {
      await api.updateAgentCustomSkill(agentId, assignment.id, { is_enabled: checked })
      loadData()
    } catch (err) {
      console.error('Failed to toggle custom skill:', err)
      alert('Failed to toggle custom skill')
    }
  }

  const handleRemove = async (assignment: any) => {
    if (!confirm(`Remove "${assignment.skill?.name}" from this agent?`)) return
    try {
      await api.removeAgentCustomSkill(agentId, assignment.id)
      loadData()
    } catch (err) {
      console.error('Failed to remove custom skill:', err)
      alert('Failed to remove custom skill')
    }
  }

  const handleAssign = async (customSkillId: number) => {
    try {
      await api.assignCustomSkillToAgent(agentId, customSkillId)
      setShowPicker(false)
      loadData()
    } catch (err) {
      console.error('Failed to assign custom skill:', err)
      alert('Failed to assign custom skill')
    }
  }

  const handleCreateAndAssign = async () => {
    if (!createForm.name.trim() || !createForm.instructions_md.trim()) return
    setCreating(true)
    try {
      const skill = await api.createCustomSkill({
        name: createForm.name.trim(),
        description: createForm.description.trim() || undefined,
        skill_type_variant: 'instruction',
        execution_mode: 'tool',
        trigger_mode: 'llm_decided',
        instructions_md: createForm.instructions_md.trim(),
        timeout_seconds: 30,
      })
      await api.assignCustomSkillToAgent(agentId, skill.id)
      setShowCreateForm(false)
      setCreateForm({ name: '', description: '', instructions_md: '' })
      loadData()
    } catch (err) {
      console.error('Failed to create custom skill:', err)
      alert('Failed to create custom skill')
    } finally {
      setCreating(false)
    }
  }

  if (loading) {
    return <div className="p-8 text-center">Loading custom skills...</div>
  }

  const enabledCount = assignments.filter((a: any) => a.is_enabled).length

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <WrenchIcon size={20} className="text-violet-400" /> Custom Skills
            <span className="text-sm font-normal text-tsushin-slate ml-1">
              {enabledCount} active / {assignments.length} assigned
            </span>
          </h2>
          <p className="text-sm text-tsushin-slate mt-1">
            Assign tenant custom skills to this agent and toggle them on/off.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowCreateForm(true)}
            className="px-4 py-2 bg-tsushin-ink text-white text-sm rounded-lg hover:bg-tsushin-surface transition-colors inline-flex items-center gap-1.5 font-medium border border-white/10"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            New Skill
          </button>
          <button
            onClick={() => setShowPicker(true)}
            disabled={unassignedAvailable.length === 0}
            className="px-4 py-2 bg-violet-600 text-white text-sm rounded-lg hover:bg-violet-700 transition-colors inline-flex items-center gap-1.5 font-medium disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Assign Skill
          </button>
        </div>
      </div>

      {/* Empty state */}
      {assignments.length === 0 && (
        <div className="text-center py-16 bg-tsushin-ink rounded-lg border border-white/5">
          <WrenchIcon size={48} className="mx-auto text-tsushin-muted mb-4" />
          <h3 className="text-lg font-medium text-white mb-2">No custom skills assigned</h3>
          {availableCustomSkills.length === 0 ? (
            <>
              <p className="text-sm text-tsushin-muted mb-6 max-w-md mx-auto">
                Your tenant has no custom skills yet. Create one here or use the Custom Skills studio for advanced options.
              </p>
              <div className="flex items-center justify-center gap-3">
                <button
                  onClick={() => setShowCreateForm(true)}
                  className="px-6 py-2.5 bg-violet-600 text-white rounded-lg hover:bg-violet-700 transition-colors inline-flex items-center gap-2 font-medium"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                  Create Custom Skill
                </button>
                <Link
                  href="/agents/custom-skills"
                  className="px-6 py-2.5 text-violet-400 hover:text-violet-300 transition-colors inline-flex items-center gap-2 font-medium text-sm"
                >
                  Custom Skills Studio
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                  </svg>
                </Link>
              </div>
            </>
          ) : (
            <>
              <p className="text-sm text-tsushin-muted mb-6 max-w-md mx-auto">
                Assign a tenant-level custom skill to give this agent a new capability.
              </p>
              <button
                onClick={() => setShowPicker(true)}
                className="px-6 py-2.5 bg-violet-600 text-white rounded-lg hover:bg-violet-700 transition-colors inline-flex items-center gap-2 font-medium"
              >
                Assign Your First Custom Skill
              </button>
            </>
          )}
        </div>
      )}

      {/* Assigned Skills Grid */}
      {assignments.length > 0 && (
        <div className="grid gap-6 md:grid-cols-2">
          {assignments.map((assignment: any) => (
            <div
              key={assignment.id}
              className={`bg-tsushin-surface/50 border rounded-lg p-4 ${
                assignment.is_enabled ? 'border-violet-600/30' : 'border-white/5'
              }`}
            >
              <div className="flex justify-between items-start mb-2">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg bg-violet-500/15 border border-violet-500/20 flex items-center justify-center">
                    <WrenchIcon size={14} className="text-violet-400" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-white">{assignment.skill?.name}</h3>
                    <p className="text-xs text-tsushin-muted">
                      {assignment.skill?.skill_type_variant} &middot; {assignment.skill?.execution_mode}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <ToggleSwitch
                    checked={assignment.is_enabled}
                    onChange={(checked) => handleToggle(assignment, checked)}
                    title={assignment.is_enabled ? 'Disable skill' : 'Enable skill'}
                  />
                  <button
                    onClick={() => handleRemove(assignment)}
                    className="text-red-400 hover:text-red-300 p-1"
                    title="Remove skill"
                  >
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                      />
                    </svg>
                  </button>
                </div>
              </div>
              {assignment.skill?.description && (
                <p className="text-xs text-tsushin-slate mt-1">{assignment.skill.description}</p>
              )}
              {assignment.skill?.scan_status && assignment.skill.scan_status !== 'clean' && (
                <span className="inline-block mt-2 px-2 py-0.5 text-xs bg-yellow-800/30 text-yellow-300 rounded-full">
                  Scan: {assignment.skill.scan_status}
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Inline Create Skill Modal */}
      {showCreateForm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-tsushin-surface rounded-xl max-w-lg w-full max-h-[85vh] overflow-hidden flex flex-col shadow-2xl border border-tsushin-border">
            <div className="bg-gradient-to-r from-violet-600 to-purple-600 px-6 py-4 flex justify-between items-center">
              <h3 className="text-lg font-semibold text-white">Create & Assign Custom Skill</h3>
              <button onClick={() => setShowCreateForm(false)} className="text-white/80 hover:text-white">
                ✕
              </button>
            </div>
            <div className="overflow-y-auto p-6 flex-1 space-y-4">
              <p className="text-xs text-tsushin-muted">
                Create an instruction-based custom skill and assign it to this agent. For script or MCP server skills, use the{' '}
                <Link href="/agents/custom-skills" className="text-violet-400 hover:underline">
                  Custom Skills Studio
                </Link>.
              </p>
              <div>
                <label className="block text-sm font-medium text-tsushin-slate mb-1">Name *</label>
                <input
                  type="text"
                  value={createForm.name}
                  onChange={(e) => setCreateForm((f) => ({ ...f, name: e.target.value }))}
                  placeholder="e.g., Policy Lookup"
                  className="w-full px-3 py-2 bg-tsushin-ink border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-violet-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-tsushin-slate mb-1">Description</label>
                <input
                  type="text"
                  value={createForm.description}
                  onChange={(e) => setCreateForm((f) => ({ ...f, description: e.target.value }))}
                  placeholder="Short description of what this skill does"
                  className="w-full px-3 py-2 bg-tsushin-ink border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-violet-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-tsushin-slate mb-1">Instructions *</label>
                <textarea
                  value={createForm.instructions_md}
                  onChange={(e) => setCreateForm((f) => ({ ...f, instructions_md: e.target.value }))}
                  placeholder="Natural language instructions for the LLM when this skill is invoked..."
                  rows={6}
                  className="w-full px-3 py-2 bg-tsushin-ink border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-violet-500 resize-y"
                />
                <p className="text-xs text-tsushin-muted mt-1">Markdown supported. Max 8,000 characters.</p>
              </div>
            </div>
            <div className="px-6 py-4 border-t border-white/5 flex justify-end gap-3">
              <button
                onClick={() => setShowCreateForm(false)}
                className="px-4 py-2 text-sm text-tsushin-slate hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateAndAssign}
                disabled={creating || !createForm.name.trim() || !createForm.instructions_md.trim()}
                className="px-6 py-2 bg-violet-600 text-white text-sm rounded-lg hover:bg-violet-700 transition-colors font-medium disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {creating ? 'Creating...' : 'Create & Assign'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Picker Modal */}
      {showPicker && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-tsushin-surface rounded-xl max-w-lg w-full max-h-[85vh] overflow-hidden flex flex-col shadow-2xl border border-tsushin-border">
            <div className="bg-gradient-to-r from-violet-600 to-purple-600 px-6 py-4 flex justify-between items-center">
              <h3 className="text-lg font-semibold text-white">Assign Custom Skill</h3>
              <button onClick={() => setShowPicker(false)} className="text-white/80 hover:text-white">
                ✕
              </button>
            </div>
            <div className="overflow-y-auto p-6 flex-1 space-y-2">
              {unassignedAvailable.length === 0 ? (
                <p className="text-sm text-tsushin-slate text-center py-8">
                  All tenant custom skills are already assigned to this agent.
                </p>
              ) : (
                unassignedAvailable.map((skill) => (
                  <button
                    key={skill.id}
                    onClick={() => handleAssign(skill.id)}
                    className="w-full text-left px-4 py-3 bg-tsushin-ink border border-white/5 rounded-lg hover:border-violet-500/40 hover:bg-tsushin-ink/70 transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-lg bg-violet-500/15 border border-violet-500/20 flex items-center justify-center flex-shrink-0">
                        <WrenchIcon size={14} className="text-violet-400" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-semibold text-white truncate">{skill.name}</div>
                        <div className="text-xs text-tsushin-muted truncate">
                          {skill.skill_type_variant} &middot; {skill.execution_mode}
                        </div>
                        {skill.description && (
                          <div className="text-xs text-tsushin-slate mt-1 line-clamp-2">{skill.description}</div>
                        )}
                      </div>
                      {skill.scan_status && skill.scan_status !== 'clean' && (
                        <span className="px-2 py-0.5 text-xs bg-yellow-800/30 text-yellow-300 rounded-full flex-shrink-0">
                          {skill.scan_status}
                        </span>
                      )}
                    </div>
                  </button>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
