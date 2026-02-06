'use client'

/**
 * AgentNode - Node component for displaying agents in the graph
 * Phase 3: Added badges for Sentinel, Memory, KB, and Skills
 * Phase 5: Added expand/collapse button for skills and KB
 * Phase 8: Added real-time processing indicator
 */

import { memo, useState, useCallback } from 'react'
import { NodeProps } from '@xyflow/react'
import BaseNode from './BaseNode'
import { AgentNodeData, MemoryIsolationMode } from '../types'

// Memory mode icons and labels
const memoryModeConfig: Record<MemoryIsolationMode, { icon: JSX.Element; label: string; color: string }> = {
  isolated: {
    icon: (
      <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
      </svg>
    ),
    label: 'Isolated Memory',
    color: 'text-blue-400',
  },
  shared: {
    icon: (
      <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M18 18.72a9.094 9.094 0 003.741-.479 3 3 0 00-4.682-2.72m.94 3.198l.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0112 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 016 18.719m12 0a5.971 5.971 0 00-.941-3.197m0 0A5.995 5.995 0 0012 12.75a5.995 5.995 0 00-5.058 2.772m0 0a3 3 0 00-4.681 2.72 8.986 8.986 0 003.74.477m.94-3.197a5.971 5.971 0 00-.94 3.197M15 6.75a3 3 0 11-6 0 3 3 0 016 0zm6 3a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0zm-13.5 0a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0z" />
      </svg>
    ),
    label: 'Shared Memory',
    color: 'text-green-400',
  },
  channel_isolated: {
    icon: (
      <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5" />
      </svg>
    ),
    label: 'Channel Isolated',
    color: 'text-amber-400',
  },
}

function AgentNode(props: NodeProps<AgentNodeData>) {
  const { data } = props
  const [showTooltip, setShowTooltip] = useState(false)

  const memoryConfig = data.memoryIsolationMode ? memoryModeConfig[data.memoryIsolationMode] : null

  // Phase 8: Real-time processing state
  const isProcessing = data.isProcessing ?? false
  const isFading = data.isFading ?? false
  const hasActiveSkill = data.hasActiveSkill ?? false

  // Phase 5: Check if agent has expandable content
  const hasExpandableContent = (data.skillsCount ?? 0) > 0 || data.hasKnowledgeBase

  // Phase 6: Check if currently loading expand data
  const isLoading = data.isLoading?.(data.id) ?? false

  // Handle expand/collapse click
  const handleExpandClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation() // Prevent node selection
    if (isLoading) return // Prevent double-clicks during loading
    if (data.isExpanded) {
      data.onCollapse?.(data.id)
    } else {
      data.onExpand?.(data.id)
    }
  }, [data, isLoading])

  return (
    <BaseNode {...props} className={isProcessing ? 'agent-node-processing' : isFading ? 'agent-node-fading' : ''}>
      <div
        className="flex flex-col relative"
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
      >
        <div className="flex items-center gap-3">
        {/* Agent Avatar */}
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center relative ${isProcessing ? 'bg-tsushin-indigo/40' : 'bg-tsushin-indigo/20'}`}>
          <svg className="w-5 h-5 text-tsushin-indigo" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
          {/* Default badge */}
          {data.isDefault && (
            <span className="absolute -top-1 -right-1 text-yellow-400 text-xs" title="Default Agent">
              *
            </span>
          )}
        </div>

        {/* Agent Info */}
        <div className="flex flex-col min-w-0">
          <div className="font-medium text-white text-sm truncate max-w-[140px]">{data.name}</div>

          {/* Model info */}
          {data.modelProvider && data.modelName && (
            <div className="text-xs text-tsushin-slate truncate max-w-[140px]">
              {data.modelProvider} / {data.modelName}
            </div>
          )}

          {/* Badges row */}
          <div className="flex items-center gap-1 mt-1 flex-wrap">
            {/* Sentinel badge */}
            {data.hasSentinelProtection && (
              <span
                className="flex items-center justify-center w-4 h-4 rounded bg-red-500/20"
                title="Sentinel Protected"
              >
                <svg className="w-2.5 h-2.5 text-red-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
                </svg>
              </span>
            )}

            {/* Memory badge */}
            {memoryConfig && (
              <span
                className={`flex items-center justify-center w-4 h-4 rounded bg-tsushin-surface/50 ${memoryConfig.color}`}
                title={memoryConfig.label}
              >
                {memoryConfig.icon}
              </span>
            )}

            {/* Knowledge Base badge */}
            {data.hasKnowledgeBase && (
              <span
                className="flex items-center justify-center w-4 h-4 rounded bg-purple-500/20"
                title="Has Knowledge Base"
              >
                <svg className="w-2.5 h-2.5 text-purple-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
                </svg>
              </span>
            )}

            {/* Skills count badge - pulses teal when skill is active on collapsed agent */}
            {(data.skillsCount ?? 0) > 0 && (
              <span
                className={`flex items-center gap-0.5 px-1 h-4 rounded text-[10px] font-medium ${
                  hasActiveSkill && !data.isExpanded
                    ? 'bg-teal-500/40 text-teal-300 animate-pulse'
                    : 'bg-teal-500/20 text-teal-400'
                }`}
                title={`${data.skillsCount} Skills${hasActiveSkill ? ' (Active)' : ''}`}
              >
                <svg className="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
                </svg>
                {data.skillsCount}
              </span>
            )}
          </div>
        </div>
        </div>

        {/* Phase 5: Expand/Collapse button */}
        {/* Phase 6: Added loading state with spinner */}
        {/* Phase 7: Added ARIA attributes for accessibility */}
        {hasExpandableContent && data.onExpand && data.onCollapse && (
          <button
            onClick={handleExpandClick}
            disabled={isLoading}
            aria-label={
              isLoading
                ? 'Loading agent features'
                : data.isExpanded
                  ? `Collapse ${data.name} features`
                  : `Expand ${(data.skillsCount ?? 0) + (data.hasKnowledgeBase ? 1 : 0)} ${data.name} features`
            }
            aria-expanded={data.isExpanded}
            aria-busy={isLoading}
            className={`
              mt-2 w-full flex items-center justify-center gap-1 py-1 rounded
              text-[10px] font-medium transition-colors
              ${isLoading
                ? 'bg-tsushin-indigo/30 text-tsushin-indigo cursor-wait'
                : data.isExpanded
                  ? 'bg-tsushin-indigo/20 text-tsushin-indigo hover:bg-tsushin-indigo/30'
                  : 'bg-tsushin-surface/50 text-tsushin-slate hover:bg-tsushin-surface hover:text-white'
              }
            `}
            title={isLoading ? 'Loading...' : data.isExpanded ? 'Collapse features' : 'Expand features'}
          >
            {isLoading ? (
              <>
                <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                Loading...
              </>
            ) : data.isExpanded ? (
              <>
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 15l7-7 7 7" />
                </svg>
                Collapse
              </>
            ) : (
              <>
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
                Expand ({(data.skillsCount ?? 0) + (data.hasKnowledgeBase ? 1 : 0)})
              </>
            )}
          </button>
        )}

        {/* Hover Tooltip */}
        {showTooltip && (
          <div className="absolute left-full ml-2 top-0 z-50 bg-tsushin-deep border border-tsushin-border rounded-lg p-3 shadow-xl min-w-[180px] pointer-events-none">
            <div className="text-xs space-y-1.5">
              <div className="flex justify-between">
                <span className="text-tsushin-slate">Model:</span>
                <span className="text-white font-medium">{data.modelProvider || 'N/A'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-tsushin-slate">Memory:</span>
                <span className="text-white font-medium capitalize">{data.memoryIsolationMode?.replace('_', ' ') || 'Default'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-tsushin-slate">Skills:</span>
                <span className="text-white font-medium">{data.skillsCount ?? 0} enabled</span>
              </div>
              {data.enabledChannels && data.enabledChannels.length > 0 && (
                <div className="flex justify-between">
                  <span className="text-tsushin-slate">Channels:</span>
                  <span className="text-white font-medium capitalize">{data.enabledChannels.join(', ')}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-tsushin-slate">Status:</span>
                <span className={`font-medium ${data.isActive ? 'text-green-400' : 'text-yellow-400'}`}>
                  {data.isActive ? 'Active' : 'Inactive'}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>
    </BaseNode>
  )
}

export default memo(AgentNode)
