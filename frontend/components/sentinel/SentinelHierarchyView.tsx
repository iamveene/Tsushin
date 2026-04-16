'use client'

import React, { useEffect, useState, useCallback } from 'react'
import { api, SentinelHierarchy, SentinelHierarchyAgent, SentinelHierarchyProfile } from '@/lib/client'

interface SentinelHierarchyViewProps {
  className?: string
}

const SOURCE_BADGES: Record<string, string> = {
  tenant: 'bg-teal-500/20 text-teal-400',
  agent: 'bg-blue-500/20 text-blue-400',
  skill: 'bg-purple-500/20 text-purple-400',
  system: 'bg-orange-500/20 text-orange-400',
  inherited: 'bg-gray-500/20 text-gray-400 border border-dashed border-gray-500/50',
  legacy: 'bg-gray-500/20 text-gray-400 border border-dashed border-gray-500/50',
}

function ProfileBadge({ profile, source }: { profile: SentinelHierarchyProfile | null; source?: string }) {
  if (!profile) {
    return (
      <span className="text-xs px-2 py-0.5 rounded-full bg-gray-500/20 text-gray-500">
        No profile
      </span>
    )
  }

  const badgeSource = source || profile.source || 'system'
  const badgeStyle = SOURCE_BADGES[badgeSource] || SOURCE_BADGES.system

  return (
    <span className={`text-xs px-2 py-0.5 rounded-full ${badgeStyle}`}>
      {profile.name}
      {profile.detection_mode && (
        <span className="ml-1 opacity-70">({profile.detection_mode})</span>
      )}
    </span>
  )
}

function ModeIndicator({ mode }: { mode?: string }) {
  const styles: Record<string, { label: string; color: string }> = {
    block: { label: 'Block', color: 'text-red-400' },
    detect_only: { label: 'Detect', color: 'text-yellow-400' },
    off: { label: 'Off', color: 'text-gray-500' },
  }
  const info = styles[mode || 'off'] || styles.off
  return <span className={`text-xs ${info.color}`}>{info.label}</span>
}

function AgentNode({ agent }: { agent: SentinelHierarchyAgent }) {
  const [expanded, setExpanded] = useState(false)
  const enabledSkills = agent.skills.filter(s => s.is_enabled)
  const hasSkills = enabledSkills.length > 0

  return (
    <div className="relative">
      {/* Agent Row */}
      <div
        className={`flex items-center gap-3 py-2 px-3 rounded-lg hover:bg-gray-800/40 transition-colors ${
          hasSkills ? 'cursor-pointer' : ''
        }`}
        onClick={() => hasSkills && setExpanded(!expanded)}
      >
        {/* Expand indicator */}
        {hasSkills ? (
          <svg
            className={`w-3.5 h-3.5 text-tsushin-slate transition-transform flex-shrink-0 ${
              expanded ? 'rotate-90' : ''
            }`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        ) : (
          <div className="w-3.5 flex-shrink-0" />
        )}

        {/* Agent icon */}
        <div className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-500/30 to-cyan-500/30 flex items-center justify-center flex-shrink-0">
          <svg className="w-3.5 h-3.5 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
        </div>

        <div className="flex items-center gap-2 min-w-0 flex-1">
          <span className="text-sm font-medium text-white truncate">{agent.name}</span>
          {!agent.is_active && (
            <span className="text-xs px-1.5 py-0.5 rounded bg-gray-600/50 text-gray-400">Inactive</span>
          )}
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {agent.profile ? (
            <ProfileBadge profile={agent.profile} source="agent" />
          ) : (
            <span className="text-xs px-2 py-0.5 rounded-full bg-gray-500/20 text-gray-400 border border-dashed border-gray-500/50">
              Inherited
            </span>
          )}
          {hasSkills && (
            <span className="text-xs text-tsushin-muted">
              {enabledSkills.length} skill{enabledSkills.length !== 1 ? 's' : ''}
            </span>
          )}
        </div>
      </div>

      {/* Skills (expanded) */}
      {expanded && enabledSkills.length > 0 && (
        <div className="border-l border-dashed border-tsushin-border/50 pl-4 ml-7 mb-2">
          {enabledSkills.map((skill) => (
            <div
              key={skill.skill_type}
              className="flex items-center gap-3 py-1.5 px-3 rounded-lg hover:bg-gray-800/30 transition-colors"
            >
              {/* Skill icon */}
              <div className="w-5 h-5 rounded bg-purple-500/15 flex items-center justify-center flex-shrink-0">
                <svg className="w-3 h-3 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>

              <span className="text-xs text-gray-300 min-w-0 flex-1 truncate">
                {skill.name || skill.skill_type}
              </span>

              <div className="flex items-center gap-2 flex-shrink-0">
                {skill.profile ? (
                  <ProfileBadge profile={skill.profile} source="skill" />
                ) : (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-gray-500/20 text-gray-400 border border-dashed border-gray-500/50">
                    Inherited
                  </span>
                )}
                {skill.effective_profile && (
                  <ModeIndicator mode={skill.effective_profile.detection_mode} />
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function SentinelHierarchyView({ className = '' }: SentinelHierarchyViewProps) {
  const [hierarchy, setHierarchy] = useState<SentinelHierarchy | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadHierarchy = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getSentinelHierarchy()
      setHierarchy(data)
    } catch (err: any) {
      setError(err.message || 'Failed to load hierarchy')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadHierarchy()
  }, [loadHierarchy])

  if (loading) {
    return (
      <div className={`flex items-center justify-center py-12 ${className}`}>
        <div className="text-center">
          <div className="relative w-10 h-10 mx-auto mb-3">
            <div className="absolute inset-0 rounded-full border-4 border-tsushin-surface"></div>
            <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-tsushin-indigo animate-spin"></div>
          </div>
          <p className="text-sm text-tsushin-slate">Loading hierarchy...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className={`flex items-center justify-center py-8 ${className}`}>
        <div className="text-center">
          <p className="text-sm text-red-400 mb-2">{error}</p>
          <button onClick={loadHierarchy} className="text-xs text-teal-400 hover:text-teal-300 underline">
            Retry
          </button>
        </div>
      </div>
    )
  }

  if (!hierarchy?.tenant) {
    return (
      <div className={`py-8 text-center ${className}`}>
        <p className="text-sm text-tsushin-slate">No hierarchy data available.</p>
      </div>
    )
  }

  const { tenant } = hierarchy

  return (
    <div className={`space-y-4 ${className}`}>
      {/* Legend */}
      <div className="flex flex-wrap gap-3 text-xs">
        <span className="text-tsushin-slate">Sources:</span>
        {[
          { label: 'Tenant', style: SOURCE_BADGES.tenant },
          { label: 'Agent', style: SOURCE_BADGES.agent },
          { label: 'Skill', style: SOURCE_BADGES.skill },
          { label: 'System Default', style: SOURCE_BADGES.system },
          { label: 'Inherited', style: SOURCE_BADGES.inherited },
        ].map(item => (
          <span key={item.label} className={`px-2 py-0.5 rounded-full ${item.style}`}>
            {item.label}
          </span>
        ))}
      </div>

      {/* Tree */}
      <div className="bg-gray-800/30 rounded-xl border border-gray-700/50 overflow-hidden">
        {/* Tenant Level */}
        <div className="p-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-teal-500/20 flex items-center justify-center flex-shrink-0">
              <svg className="w-5 h-5 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
              </svg>
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <h3 className="text-base font-semibold text-white">{tenant.name || 'Tenant'}</h3>
                <span className="text-xs px-1.5 py-0.5 rounded bg-teal-500/10 text-teal-400 border border-teal-500/20">
                  Root
                </span>
              </div>
              <p className="text-xs text-tsushin-slate mt-0.5">
                {tenant.agents.length} agent{tenant.agents.length !== 1 ? 's' : ''} configured
              </p>
            </div>

            <div className="flex-shrink-0">
              {tenant.profile ? (
                <ProfileBadge profile={tenant.profile} source="tenant" />
              ) : (
                <span className="text-xs px-2 py-0.5 rounded-full bg-orange-500/20 text-orange-400">
                  System Default
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Agents */}
        {tenant.agents.length > 0 ? (
          <div className="border-t border-gray-700/50">
            <div className="border-l border-dashed border-tsushin-border/50 pl-4 ml-6 py-2">
              {tenant.agents.map((agent) => (
                <AgentNode key={agent.id} agent={agent} />
              ))}
            </div>
          </div>
        ) : (
          <div className="border-t border-gray-700/50 p-6 text-center">
            <p className="text-sm text-tsushin-slate">No agents configured yet.</p>
          </div>
        )}
      </div>

      {/* Refresh */}
      <div className="flex justify-end">
        <button
          onClick={loadHierarchy}
          className="flex items-center gap-1.5 text-xs text-tsushin-slate hover:text-white transition-colors"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Refresh
        </button>
      </div>
    </div>
  )
}
