'use client'

import { useState, useEffect } from 'react'
import { api } from '@/lib/client'
import type { AgentCommPermission } from '@/lib/client'
import type { BuilderGhostAgentData } from '../types'
import A2APermissionConfigForm from './A2APermissionConfigForm'
import { AgentAvatarIcon } from '../avatars/AgentAvatars'

interface GhostAgentInfoPanelProps {
  data: BuilderGhostAgentData
  currentAgentId: number
}

export default function GhostAgentInfoPanel({ data, currentAgentId }: GhostAgentInfoPanelProps) {
  const [permission, setPermission] = useState<AgentCommPermission | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [editingPermission, setEditingPermission] = useState(false)

  useEffect(() => {
    setIsLoading(true)
    setPermission(null)
    api.getAgentCommPermissions()
      .then(perms => {
        const match = perms.find(p =>
          (p.source_agent_id === currentAgentId && p.target_agent_id === data.agentId) ||
          (p.source_agent_id === data.agentId && p.target_agent_id === currentAgentId)
        )
        setPermission(match ?? null)
      })
      .catch(() => setPermission(null))
      .finally(() => setIsLoading(false))
  }, [data.agentId, currentAgentId])

  if (editingPermission) {
    return (
      <A2APermissionConfigForm
        sourceAgentId={currentAgentId}
        targetAgentId={data.agentId}
        permission={permission}
        onClose={() => setEditingPermission(false)}
        onSaved={(updated) => { setPermission(updated); setEditingPermission(false) }}
      />
    )
  }

  return (
    <div className="space-y-4">
      {/* Agent identity */}
      <div className="flex items-center gap-3 pb-3 border-b border-tsushin-border">
        <AgentAvatarIcon slug={data.avatar} size="sm" />
        <div>
          <p className="text-sm font-medium text-white">{data.agentName}</p>
          <p className="text-xs text-tsushin-slate">Peer agent (A2A)</p>
        </div>
      </div>

      {/* Permission details */}
      {isLoading ? (
        <p className="text-xs text-tsushin-muted">Loading permission...</p>
      ) : permission ? (
        <div className="space-y-3">
          <div className="config-field">
            <label>Direction</label>
            <p className="text-sm text-white">
              {permission.source_agent_id === currentAgentId
                ? 'Outbound (you → peer)'
                : 'Inbound (peer → you)'}
            </p>
          </div>
          <div className="config-field">
            <label>Status</label>
            <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${permission.is_enabled ? 'bg-green-500/20 text-green-300' : 'bg-gray-500/20 text-gray-400'}`}>
              {permission.is_enabled ? 'Enabled' : 'Disabled'}
            </span>
          </div>
          <div className="config-field">
            <label>Max Depth</label>
            <p className="text-sm text-white">{permission.max_depth}</p>
          </div>
          <div className="config-field">
            <label>Rate Limit</label>
            <p className="text-sm text-white">{permission.rate_limit_rpm} req/min</p>
          </div>
        </div>
      ) : (
        <p className="text-xs text-tsushin-muted">No direct permission found.</p>
      )}

      <div className="border-t border-tsushin-border pt-3">
        <button
          onClick={() => setEditingPermission(true)}
          className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 transition-colors"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125" />
          </svg>
          Edit Permission
        </button>
      </div>
    </div>
  )
}
