'use client'

/**
 * Studio → A2A Communications
 *
 * Group-level configuration surface for agent-to-agent communication. Lets the
 * tenant-admin define which agents are allowed to talk to which other agents,
 * toggle per-row safety knobs (max depth, rate limit, allow_target_skills),
 * enable/disable a rule, or delete it.
 *
 * This is the configuration home for A2A. Observability (session log, stats)
 * lives in Watcher → A2A Comms.
 */

import { useEffect, useState, useCallback } from 'react'
import { useToast } from '@/contexts/ToastContext'
import { useGlobalRefresh } from '@/hooks/useGlobalRefresh'
import {
  api,
  Agent,
  AgentCommPermission,
} from '@/lib/client'

export default function A2APermissionsManager() {
  const toast = useToast()

  const [agents, setAgents] = useState<Agent[]>([])
  const [permissions, setPermissions] = useState<AgentCommPermission[]>([])
  const [loading, setLoading] = useState(true)
  const [permissionsLoading, setPermissionsLoading] = useState(false)

  const [showAddModal, setShowAddModal] = useState(false)
  const [newPermission, setNewPermission] = useState({
    source_agent_id: 0,
    target_agent_id: 0,
    max_depth: 3,
    rate_limit_rpm: 30,
    // Default ON in the UI: a tenant admin clicking "Add Permission" almost always
    // wants the target to actually do its job (read mailbox, run a tool) when asked.
    // The DB-level default stays false (defense in depth — see models.py:4158).
    allow_target_skills: true,
  })
  const [savingPermission, setSavingPermission] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [togglingTargetSkillsId, setTogglingTargetSkillsId] = useState<number | null>(null)

  const loadAgents = useCallback(async () => {
    try {
      const agentsData = await api.getAgents()
      setAgents(agentsData)
    } catch (err: any) {
      toast.error('Load Failed', err.message || 'Failed to load agents')
    }
  }, [toast])

  const loadPermissions = useCallback(async () => {
    setPermissionsLoading(true)
    try {
      const data = await api.getAgentCommPermissions()
      setPermissions(data)
    } catch (err: any) {
      toast.error('Load Failed', err.message || 'Failed to load permissions')
    } finally {
      setPermissionsLoading(false)
    }
  }, [toast])

  const loadAll = useCallback(async () => {
    setLoading(true)
    await Promise.all([loadAgents(), loadPermissions()])
    setLoading(false)
  }, [loadAgents, loadPermissions])

  useEffect(() => {
    loadAll()
  }, [loadAll])

  useGlobalRefresh(() => loadAll())

  const handleCreatePermission = async () => {
    if (!newPermission.source_agent_id || !newPermission.target_agent_id) {
      toast.warning('Validation', 'Please select both source and target agents')
      return
    }
    if (newPermission.source_agent_id === newPermission.target_agent_id) {
      toast.warning('Validation', 'Source and target agents must be different')
      return
    }
    setSavingPermission(true)
    try {
      await api.createAgentCommPermission(newPermission)
      toast.success('Permission created successfully')
      setShowAddModal(false)
      setNewPermission({ source_agent_id: 0, target_agent_id: 0, max_depth: 3, rate_limit_rpm: 30, allow_target_skills: true })
      loadPermissions()
    } catch (err: any) {
      toast.error('Create Failed', err.message || 'Failed to create permission')
    } finally {
      setSavingPermission(false)
    }
  }

  const handleTogglePermission = async (perm: AgentCommPermission) => {
    try {
      await api.updateAgentCommPermission(perm.id, { is_enabled: !perm.is_enabled })
      toast.success(`Permission ${perm.is_enabled ? 'disabled' : 'enabled'}`)
      loadPermissions()
    } catch (err: any) {
      toast.error('Update Failed', err.message || 'Failed to update permission')
    }
  }

  const handleToggleTargetSkills = async (perm: AgentCommPermission) => {
    if (togglingTargetSkillsId === perm.id) return
    setTogglingTargetSkillsId(perm.id)
    try {
      await api.updateAgentCommPermission(perm.id, { allow_target_skills: !perm.allow_target_skills })
      toast.success(perm.allow_target_skills ? 'Target skills restricted' : 'Target skills allowed')
      loadPermissions()
    } catch (err: any) {
      toast.error('Update Failed', err.message || 'Failed to update permission')
    } finally {
      setTogglingTargetSkillsId(null)
    }
  }

  const handleDeletePermission = async (id: number) => {
    if (!window.confirm('Are you sure you want to delete this permission? This action cannot be undone.')) return
    setDeletingId(id)
    try {
      await api.deleteAgentCommPermission(id)
      toast.success('Permission deleted')
      loadPermissions()
    } catch (err: any) {
      toast.error('Delete Failed', err.message || 'Failed to delete permission')
    } finally {
      setDeletingId(null)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <div className="relative w-12 h-12 mx-auto mb-4">
            <div className="absolute inset-0 rounded-full border-4 border-tsushin-surface"></div>
            <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-tsushin-indigo animate-spin"></div>
          </div>
          <p className="text-tsushin-slate font-medium">Loading...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="glass-card rounded-xl overflow-hidden">
        <div className="p-6 border-b border-tsushin-border/50 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-display font-semibold text-white">Permission Rules</h2>
            <p className="text-sm text-tsushin-slate mt-1">
              Define which agents can send messages to which other agents. Each rule is directional (source → target) and controls max delegation depth, per-minute rate limit, and whether the target may use its own skills when invoked.
            </p>
            <p className="text-xs text-tsushin-muted mt-2">
              Looking for session logs or stats? See <a href="/" className="text-teal-400 hover:text-teal-300 underline">Watcher → A2A Comms</a>.
            </p>
          </div>
          <button
            onClick={() => setShowAddModal(true)}
            className="shrink-0 px-4 py-2 bg-gradient-to-r from-teal-500 to-cyan-400 text-white rounded-lg text-sm font-medium hover:opacity-90 transition-opacity"
          >
            Add Permission
          </button>
        </div>

        {permissionsLoading ? (
          <div className="p-8 text-center">
            <p className="text-tsushin-slate">Loading permissions...</p>
          </div>
        ) : permissions.length === 0 ? (
          <div className="p-8 text-center">
            <p className="text-tsushin-slate">No permission rules configured.</p>
            <p className="text-sm text-tsushin-muted mt-1">Add a permission to allow agents to communicate.</p>
          </div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-tsushin-border/30">
                <th className="px-6 py-3 text-left text-xs font-medium text-tsushin-slate uppercase tracking-wider">Source Agent</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-tsushin-slate uppercase tracking-wider">Target Agent</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-tsushin-slate uppercase tracking-wider">Max Depth</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-tsushin-slate uppercase tracking-wider">Rate Limit</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-tsushin-slate uppercase tracking-wider" title="Allow the target agent to use its own skills (gmail, sandboxed_tools, …) when invoked via A2A">Target Skills</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-tsushin-slate uppercase tracking-wider">Status</th>
                <th className="px-6 py-3 text-right text-xs font-medium text-tsushin-slate uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-tsushin-border/30">
              {permissions.map((perm) => (
                <tr key={perm.id} className="hover:bg-gray-800/30 transition-colors">
                  <td className="px-6 py-4 text-sm text-white">
                    {perm.source_agent_name || `Agent #${perm.source_agent_id}`}
                  </td>
                  <td className="px-6 py-4 text-sm text-white">
                    {perm.target_agent_name || `Agent #${perm.target_agent_id}`}
                  </td>
                  <td className="px-6 py-4 text-sm text-tsushin-slate">{perm.max_depth}</td>
                  <td className="px-6 py-4 text-sm text-tsushin-slate">{perm.rate_limit_rpm} RPM</td>
                  <td className="px-6 py-4">
                    <button
                      onClick={() => handleToggleTargetSkills(perm)}
                      disabled={togglingTargetSkillsId === perm.id}
                      title={perm.allow_target_skills
                        ? 'Target may use its own skills during A2A (click to restrict)'
                        : 'Target runs without tools during A2A (click to allow its own skills)'}
                      className={`relative inline-flex h-5 w-10 items-center rounded-full transition-colors disabled:opacity-50 ${
                        perm.allow_target_skills ? 'bg-amber-500' : 'bg-gray-600'
                      }`}
                    >
                      <span
                        className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                          perm.allow_target_skills ? 'translate-x-5' : 'translate-x-1'
                        }`}
                      />
                    </button>
                  </td>
                  <td className="px-6 py-4">
                    <button
                      onClick={() => handleTogglePermission(perm)}
                      className={`relative inline-flex h-5 w-10 items-center rounded-full transition-colors ${
                        perm.is_enabled ? 'bg-teal-500' : 'bg-gray-600'
                      }`}
                    >
                      <span
                        className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                          perm.is_enabled ? 'translate-x-5' : 'translate-x-1'
                        }`}
                      />
                    </button>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <button
                      onClick={() => handleDeletePermission(perm.id)}
                      disabled={deletingId === perm.id}
                      className="text-red-400 hover:text-red-300 text-sm transition-colors disabled:opacity-50"
                    >
                      {deletingId === perm.id ? 'Deleting...' : 'Delete'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showAddModal && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
          onClick={() => setShowAddModal(false)}
        >
          <div
            className="bg-tsushin-elevated rounded-xl max-w-md w-full shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-6 border-b border-tsushin-border/50">
              <h3 className="text-lg font-semibold text-white">Add Communication Permission</h3>
              <p className="text-sm text-tsushin-slate mt-1">
                Allow one agent to send messages to another
              </p>
            </div>

            <div className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Source Agent</label>
                <select
                  value={newPermission.source_agent_id || ''}
                  onChange={(e) => setNewPermission({ ...newPermission, source_agent_id: parseInt(e.target.value) || 0 })}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
                >
                  <option value="">Select source agent...</option>
                  {agents.map((a) => (
                    <option key={a.id} value={a.id}>{a.contact_name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Target Agent</label>
                <select
                  value={newPermission.target_agent_id || ''}
                  onChange={(e) => setNewPermission({ ...newPermission, target_agent_id: parseInt(e.target.value) || 0 })}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
                >
                  <option value="">Select target agent...</option>
                  {agents.map((a) => (
                    <option key={a.id} value={a.id}>{a.contact_name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Max Depth</label>
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={newPermission.max_depth}
                  onChange={(e) => setNewPermission({ ...newPermission, max_depth: parseInt(e.target.value) || 3 })}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
                />
                <p className="text-xs text-tsushin-muted mt-1">Maximum chain depth for recursive agent calls (1-10)</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Rate Limit (RPM)</label>
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={newPermission.rate_limit_rpm}
                  onChange={(e) => setNewPermission({ ...newPermission, rate_limit_rpm: parseInt(e.target.value) || 10 })}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
                />
                <p className="text-xs text-tsushin-muted mt-1">Maximum requests per minute</p>
              </div>

              <div>
                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={newPermission.allow_target_skills}
                    onChange={(e) => setNewPermission({ ...newPermission, allow_target_skills: e.target.checked })}
                    className="mt-1 h-4 w-4 rounded border-gray-600 bg-gray-800 text-amber-500 focus:ring-2 focus:ring-amber-500"
                  />
                  <span>
                    <span className="block text-sm font-medium text-gray-300">
                      Allow target to use its own skills <span className="text-tsushin-muted font-normal">(recommended)</span>
                    </span>
                    <span className="block text-xs text-tsushin-muted mt-0.5">
                      The target agent can use its gmail, sandboxed_tools, shell, etc. when invoked through A2A.
                      Uncheck for pure LLM-knowledge replies. Depth, rate limit, and Sentinel still apply.
                    </span>
                  </span>
                </label>
                {newPermission.allow_target_skills && (
                  <div className="mt-2 ml-7 px-3 py-2 rounded-md bg-amber-500/10 border border-amber-500/30 text-xs text-amber-200">
                    <strong className="font-medium">Heads up:</strong> the source agent will be able to invoke the target's tools indirectly.
                    Only enable for source agents you trust to act on your behalf (capability amplification).
                  </div>
                )}
              </div>
            </div>

            <div className="p-6 border-t border-tsushin-border/50 flex justify-end gap-3">
              <button
                onClick={() => setShowAddModal(false)}
                className="px-4 py-2 text-tsushin-slate hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleCreatePermission}
                disabled={savingPermission}
                className="px-4 py-2 bg-gradient-to-r from-teal-500 to-cyan-400 text-white rounded-lg font-medium transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                {savingPermission ? 'Creating...' : 'Create Permission'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
