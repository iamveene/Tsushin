'use client'

import { memo, useCallback } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import type { BuilderGroupData, ProfileCategoryId } from '../types'
import { CATEGORY_DISPLAY } from '../types'

const categoryIcons: Record<ProfileCategoryId, JSX.Element> = {
  channels: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 01-.825-.242m9.345-8.334a2.126 2.126 0 00-.476-.095 48.64 48.64 0 00-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0011.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155" />
    </svg>
  ),
  skills: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 7.5l-9-5.25L3 7.5m18 0l-9 5.25m9-5.25v9l-9 5.25M3 7.5l9 5.25M3 7.5v9l9 5.25m0-9v9" />
    </svg>
  ),
  tools: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M11.42 15.17l-5.66 5.66a2.12 2.12 0 01-3-3l5.66-5.66m3-3l5.66-5.66a2.12 2.12 0 013 3l-5.66 5.66m-3 3l-3-3m3 3l-1.5 1.5M15.17 11.42l1.5-1.5" />
    </svg>
  ),
  knowledge: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
    </svg>
  ),
  persona: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
    </svg>
  ),
  security: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
    </svg>
  ),
  memory: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 0v3.75m-16.5-3.75v3.75m16.5 0v3.75C20.25 16.153 16.556 18 12 18s-8.25-1.847-8.25-4.125v-3.75m16.5 0c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125" />
    </svg>
  ),
}

// Color mapping for handle dots
const handleColors: Record<string, string> = {
  'text-blue-400': '#60A5FA',
  'text-teal-400': '#2DD4BF',
  'text-orange-400': '#FB923C',
  'text-violet-400': '#A78BFA',
}

function BuilderGroupNode({ data, selected }: NodeProps<BuilderGroupData>) {
  const display = CATEGORY_DISPLAY[data.categoryId]
  const icon = categoryIcons[data.categoryId]
  const handleColor = handleColors[display.color] || '#8B929E'

  const handleExpandClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    if (data.isExpanded) {
      data.onCollapse(data.categoryId)
    } else {
      data.onExpand(data.categoryId)
    }
  }, [data])

  return (
    <div
      className={`
        builder-group-node group-${data.categoryId}
        relative px-3 py-2.5 rounded-lg border min-w-[160px]
        transition-all duration-200
        ${selected
          ? `${display.borderColor} ${display.bgColor} shadow-lg`
          : `border-tsushin-border bg-tsushin-surface hover:${display.borderColor}`
        }
        ${data.isExpanded ? 'expanded shadow-md' : ''}
      `}
    >
      {/* Target handle (from agent) */}
      <Handle
        type="target"
        position={Position.Left}
        className="!w-2.5 !h-2.5 !border-2 !border-tsushin-deep"
        style={{ backgroundColor: handleColor }}
      />

      {/* Source handle (to children - hidden when collapsed) */}
      <Handle
        type="source"
        position={Position.Right}
        className={`!w-2.5 !h-2.5 !border-2 !border-tsushin-deep ${!data.isExpanded ? '!opacity-0' : ''}`}
        style={{
          backgroundColor: handleColor,
          visibility: data.isExpanded ? 'visible' : 'hidden',
        }}
      />

      <div className="flex items-center gap-2.5">
        {/* Category Icon */}
        <div className={`flex-shrink-0 ${display.color}`}>
          {icon}
        </div>

        {/* Label + Count */}
        <div className="flex flex-col min-w-0 flex-1">
          <div className="text-xs font-medium text-white">
            {data.categoryLabel}
          </div>
          <div className="flex items-center gap-1 mt-0.5">
            <span className={`group-count-badge ${display.bgColor} ${display.color}`}>
              {data.childCount} {data.childCount === 1
                ? data.categoryId === 'knowledge' ? 'doc' : data.categoryId.slice(0, -1)
                : data.categoryId === 'knowledge' ? 'docs' : data.categoryId}
            </span>
          </div>
        </div>

        {/* Expand/Collapse button */}
        <button
          onClick={handleExpandClick}
          aria-label={data.isExpanded ? `Collapse ${data.categoryLabel}` : `Expand ${data.childCount} ${data.categoryLabel}`}
          aria-expanded={data.isExpanded}
          className={`
            p-1 rounded transition-colors
            ${data.isExpanded
              ? `${display.bgColor} ${display.color}`
              : 'bg-tsushin-surface/50 text-tsushin-slate hover:text-white'
            }
          `}
        >
          <svg
            className={`w-3.5 h-3.5 expand-button transition-transform duration-200 ${data.isExpanded ? 'rotate-180' : ''}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </button>
      </div>
    </div>
  )
}

export default memo(BuilderGroupNode)
