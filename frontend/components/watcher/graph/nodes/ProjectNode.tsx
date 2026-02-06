'use client'

/**
 * ProjectNode - Node component for displaying projects in the graph
 * Phase 4: Projects View Implementation
 */

import { memo, useState } from 'react'
import { NodeProps, Handle, Position } from '@xyflow/react'
import { ProjectNodeData } from '../types'
import { FolderIcon, PROJECT_ICON_MAP, ArchiveIcon } from '@/components/ui/icons'

function ProjectNode(props: NodeProps<ProjectNodeData>) {
  const { data, selected } = props
  const [showTooltip, setShowTooltip] = useState(false)

  // Parse color for styling - handle both hex and named colors
  const accentColor = data.color || '#6366f1'

  return (
    <div
      className={`
        px-4 py-3 rounded-xl border transition-all duration-200
        ${selected
          ? 'border-tsushin-indigo shadow-glow-sm'
          : 'border-tsushin-border hover:border-tsushin-muted'
        }
        ${data.isArchived
          ? 'bg-tsushin-surface/50 opacity-60'
          : 'bg-tsushin-surface'
        }
      `}
    >
      {/* Source handle (right side) */}
      <Handle
        type="source"
        position={Position.Right}
        className="!bg-tsushin-indigo !border-tsushin-surface !w-3 !h-3"
      />

      {/* Target handle (left side) */}
      <Handle
        type="target"
        position={Position.Left}
        className="!bg-tsushin-accent !border-tsushin-surface !w-3 !h-3"
      />

      <div
        className="flex items-center gap-3 relative"
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
      >
        {/* Project Avatar with Icon */}
        <div
          className="w-10 h-10 rounded-lg flex items-center justify-center text-lg relative"
          style={{ backgroundColor: `${accentColor}20` }}
        >
          {(() => { const iconEntry = PROJECT_ICON_MAP.find(i => i.label === data.icon); return iconEntry ? <iconEntry.Icon size={20} className="text-current" /> : <FolderIcon size={20} className="text-current" /> })()}
          {/* Archived badge */}
          {data.isArchived && (
            <span className="absolute -top-1 -right-1 text-yellow-400" title="Archived">
              <ArchiveIcon size={12} />
            </span>
          )}
        </div>

        {/* Project Info */}
        <div className="flex flex-col min-w-0">
          <div className="font-medium text-white text-sm truncate max-w-[140px]">{data.name}</div>

          {/* Project type indicator */}
          <div className="text-xs text-tsushin-slate">
            Project
          </div>

          {/* Badges row */}
          <div className="flex items-center gap-1 mt-1 flex-wrap">
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

            {/* Document count badge */}
            {(data.documentCount ?? 0) > 0 && (
              <span
                className="flex items-center gap-0.5 px-1 h-4 rounded bg-blue-500/20 text-blue-400 text-[10px] font-medium"
                title={`${data.documentCount} Documents`}
              >
                <svg className="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                </svg>
                {data.documentCount}
              </span>
            )}

            {/* Agent access count badge */}
            {(data.agentAccessCount ?? 0) > 0 && (
              <span
                className="flex items-center gap-0.5 px-1 h-4 rounded bg-green-500/20 text-green-400 text-[10px] font-medium"
                title={`${data.agentAccessCount} Agents with access`}
              >
                <svg className="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
                {data.agentAccessCount}
              </span>
            )}
          </div>
        </div>

        {/* Hover Tooltip */}
        {showTooltip && (
          <div className="absolute left-full ml-2 top-0 z-50 bg-tsushin-deep border border-tsushin-border rounded-lg p-3 shadow-xl min-w-[180px] pointer-events-none">
            <div className="text-xs space-y-1.5">
              <div className="flex justify-between">
                <span className="text-tsushin-slate">Documents:</span>
                <span className="text-white font-medium">{data.documentCount ?? 0}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-tsushin-slate">Agents:</span>
                <span className="text-white font-medium">{data.agentAccessCount ?? 0} with access</span>
              </div>
              <div className="flex justify-between">
                <span className="text-tsushin-slate">Status:</span>
                <span className={`font-medium ${data.isArchived ? 'text-yellow-400' : 'text-green-400'}`}>
                  {data.isArchived ? 'Archived' : 'Active'}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default memo(ProjectNode)
