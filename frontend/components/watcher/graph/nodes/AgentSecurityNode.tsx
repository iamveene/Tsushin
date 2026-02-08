'use client'

/**
 * AgentSecurityNode - Agent node for security hierarchy graph
 * Phase F (v1.6.0): Shows agent with assigned/effective Sentinel profile
 * Supports expand/collapse to show skill-security child nodes
 */

import { memo, useState, useCallback } from 'react'
import { NodeProps, Handle, Position } from '@xyflow/react'
import { AgentSecurityNodeData, SecurityDetectionMode } from '../types'

const modeColors: Record<SecurityDetectionMode, { bg: string; text: string }> = {
  block: { bg: 'bg-red-500/20', text: 'text-red-400' },
  detect_only: { bg: 'bg-amber-500/20', text: 'text-amber-400' },
  off: { bg: 'bg-gray-500/20', text: 'text-gray-400' },
}

const sourceColors: Record<string, { bg: string; text: string }> = {
  skill: { bg: 'bg-purple-500/20', text: 'text-purple-400' },
  agent: { bg: 'bg-blue-500/20', text: 'text-blue-400' },
  tenant: { bg: 'bg-teal-500/20', text: 'text-teal-400' },
  system: { bg: 'bg-orange-500/20', text: 'text-orange-400' },
}

function AgentSecurityNode(props: NodeProps<AgentSecurityNodeData>) {
  const { data, selected } = props
  const [showTooltip, setShowTooltip] = useState(false)

  const hasExplicitProfile = data.profile !== null
  const effectiveSource = data.effectiveProfile?.source || 'system'
  const effectiveName = data.effectiveProfile?.name || 'None'
  const mode = modeColors[data.detectionMode]
  const source = sourceColors[effectiveSource] || sourceColors.system
  const hasSkills = data.skillsCount > 0

  const handleExpandClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    if (data.isExpanded) {
      data.onCollapse?.(data.id)
    } else {
      data.onExpand?.(data.id)
    }
  }, [data])

  return (
    <div
      className={`
        relative px-4 py-3 rounded-lg border-2 min-w-[200px]
        transition-all duration-200
        ${selected
          ? 'border-tsushin-indigo bg-tsushin-surface shadow-lg shadow-tsushin-indigo/20'
          : hasExplicitProfile
            ? 'border-blue-500/50 bg-tsushin-deep hover:border-blue-500/70'
            : 'border-dashed border-tsushin-border bg-tsushin-deep hover:border-tsushin-border-hover'
        }
        ${!data.isActive ? 'opacity-50' : ''}
        ${!data.isEnabled ? 'ring-1 ring-red-500/30' : ''}
      `}
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      {/* Target handle (top - from tenant) */}
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-tsushin-indigo !w-2 !h-2 !border-2 !border-tsushin-deep"
      />
      {/* Source handle (bottom - to skills) */}
      <Handle
        type="source"
        position={Position.Bottom}
        className="!bg-tsushin-indigo !w-2 !h-2 !border-2 !border-tsushin-deep"
      />

      <div className="flex items-center gap-3">
        {/* Agent icon */}
        <div className="w-8 h-8 rounded-lg bg-tsushin-indigo/20 flex items-center justify-center shrink-0">
          <svg className="w-4 h-4 text-tsushin-indigo" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19 14.5M14.25 3.104c.251.023.501.05.75.082M19 14.5l-2.47-2.47m0 0L19 9.56m-2.47 2.47H14.5m-5 0H7.53m0 0L5 9.56m2.53 2.47L5 14.5" />
          </svg>
        </div>

        <div className="flex flex-col min-w-0 flex-1">
          {/* Agent name */}
          <div className="font-medium text-white text-sm truncate max-w-[150px]">
            {data.name}
          </div>

          {/* Badges row */}
          <div className="flex items-center gap-1 mt-1 flex-wrap">
            {/* Profile name badge */}
            <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${mode.bg} ${mode.text}`}>
              {effectiveName}
            </span>
            {/* Source badge */}
            <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${source.bg} ${source.text} capitalize`}>
              {hasExplicitProfile ? 'Custom' : `Inherited (${effectiveSource})`}
            </span>
            {/* Skills count badge */}
            {hasSkills && (
              <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-tsushin-surface text-tsushin-slate">
                {data.skillsCount} skill{data.skillsCount !== 1 ? 's' : ''}
              </span>
            )}
            {/* Inactive badge */}
            {!data.isActive && (
              <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-gray-500/20 text-gray-400">
                Inactive
              </span>
            )}
          </div>
        </div>

        {/* Expand/Collapse button */}
        {hasSkills && (
          <button
            onClick={handleExpandClick}
            className="w-6 h-6 rounded flex items-center justify-center shrink-0 hover:bg-tsushin-surface transition-colors"
            title={data.isExpanded ? 'Collapse skills' : 'Expand skills'}
          >
            <svg
              className={`w-3.5 h-3.5 text-tsushin-slate transition-transform duration-200 ${data.isExpanded ? 'rotate-180' : ''}`}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
            </svg>
          </button>
        )}
      </div>

      {/* Hover tooltip */}
      {showTooltip && (
        <div className="absolute left-full ml-2 top-0 z-50 bg-tsushin-deep border border-tsushin-border rounded-lg p-3 shadow-xl min-w-[200px] pointer-events-none">
          <div className="text-xs space-y-1.5">
            <div className="flex justify-between gap-4">
              <span className="text-tsushin-slate">Agent:</span>
              <span className="text-white font-medium">{data.name}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-tsushin-slate">Effective Profile:</span>
              <span className="text-white font-medium">{effectiveName}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-tsushin-slate">Mode:</span>
              <span className={`font-medium ${mode.text}`}>{data.detectionMode.replace('_', ' ')}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-tsushin-slate">Source:</span>
              <span className={`font-medium ${source.text} capitalize`}>{effectiveSource}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-tsushin-slate">Assignment:</span>
              <span className={`font-medium ${hasExplicitProfile ? 'text-blue-400' : 'text-tsushin-slate'}`}>
                {hasExplicitProfile ? `Explicit: ${data.profile?.name}` : 'Inherited'}
              </span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-tsushin-slate">Aggressiveness:</span>
              <span className="text-white font-medium">{data.aggressivenessLevel}</span>
            </div>
            {hasSkills && (
              <div className="flex justify-between gap-4">
                <span className="text-tsushin-slate">Skills:</span>
                <span className="text-white font-medium">{data.skillsCount}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default memo(AgentSecurityNode)
