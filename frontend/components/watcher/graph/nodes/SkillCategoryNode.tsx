'use client'

/**
 * SkillCategoryNode - Groups multiple skills by category to reduce graph clutter
 * Phase 7: Skill grouping for agents with many skills (>4)
 */

import { memo, useCallback } from 'react'
import { NodeProps, Handle, Position } from '@xyflow/react'
import { SkillCategoryNodeData } from '../types'

// Category configuration with colors and icons
const categoryConfig: Record<string, { color: string; bgColor: string; borderColor: string; icon: JSX.Element; displayName: string }> = {
  search: {
    color: 'text-blue-400',
    bgColor: 'bg-blue-500/10',
    borderColor: 'border-blue-500/30',
    displayName: 'Search',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
      </svg>
    ),
  },
  audio: {
    color: 'text-orange-400',
    bgColor: 'bg-orange-500/10',
    borderColor: 'border-orange-500/30',
    displayName: 'Audio',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />
      </svg>
    ),
  },
  integration: {
    color: 'text-red-400',
    bgColor: 'bg-red-500/10',
    borderColor: 'border-red-500/30',
    displayName: 'Integrations',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244" />
      </svg>
    ),
  },
  automation: {
    color: 'text-purple-400',
    bgColor: 'bg-purple-500/10',
    borderColor: 'border-purple-500/30',
    displayName: 'Automation',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12a7.5 7.5 0 0015 0m-15 0a7.5 7.5 0 1115 0m-15 0H3m16.5 0H21m-1.5 0H12m-8.457 3.077l1.41-.513m14.095-5.13l1.41-.513M5.106 17.785l1.15-.964m11.49-9.642l1.149-.964M7.501 19.795l.75-1.3m7.5-12.99l.75-1.3m-6.063 16.658l.26-1.477m2.605-14.772l.26-1.477m0 17.726l-.26-1.477M10.698 4.614l-.26-1.477M16.5 19.794l-.75-1.299M7.5 4.205L12 12m6.894 5.785l-1.149-.964M6.256 7.178l-1.15-.964m15.352 8.864l-1.41-.513M4.954 9.435l-1.41-.514M12.002 12l-3.75 6.495" />
      </svg>
    ),
  },
  system: {
    color: 'text-green-400',
    bgColor: 'bg-green-500/10',
    borderColor: 'border-green-500/30',
    displayName: 'System',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 7.5l3 2.25-3 2.25m4.5 0h3m-9 8.25h13.5A2.25 2.25 0 0021 18V6a2.25 2.25 0 00-2.25-2.25H5.25A2.25 2.25 0 003 6v12a2.25 2.25 0 002.25 2.25z" />
      </svg>
    ),
  },
  media: {
    color: 'text-pink-400',
    bgColor: 'bg-pink-500/10',
    borderColor: 'border-pink-500/30',
    displayName: 'Media',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5zm10.5-11.25h.008v.008h-.008V8.25zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z" />
      </svg>
    ),
  },
  travel: {
    color: 'text-cyan-400',
    bgColor: 'bg-cyan-500/10',
    borderColor: 'border-cyan-500/30',
    displayName: 'Travel',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
      </svg>
    ),
  },
  special: {
    color: 'text-amber-400',
    bgColor: 'bg-amber-500/10',
    borderColor: 'border-amber-500/30',
    displayName: 'Special',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 001.423 1.423l1.183.394-1.183.394a2.25 2.25 0 00-1.423 1.423z" />
      </svg>
    ),
  },
  other: {
    color: 'text-teal-400',
    bgColor: 'bg-teal-500/10',
    borderColor: 'border-teal-500/30',
    displayName: 'Other',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
      </svg>
    ),
  },
}

function SkillCategoryNode(props: NodeProps<SkillCategoryNodeData>) {
  const { data, selected } = props

  const catConfig = categoryConfig[data.category] || categoryConfig.other
  const isActive = data.isActive ?? false
  const isFading = data.isFading ?? false

  const handleExpandClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    if (data.isExpanded) {
      data.onCollapse?.(data.parentAgentId, data.category)
    } else {
      data.onExpand?.(data.parentAgentId, data.category)
    }
  }, [data])

  return (
    <div
      className={`
        relative px-3 py-2 rounded-lg border min-w-[140px]
        transition-all duration-200
        ${selected
          ? `${catConfig.borderColor} ${catConfig.bgColor} shadow-lg`
          : `border-tsushin-border bg-tsushin-surface hover:${catConfig.borderColor}`
        }
        ${isActive && !isFading ? 'skill-node-active' : isFading ? 'skill-node-fading' : ''}
      `}
    >
      {/* Connection handle - target (connects from agent on the left in LR layout) */}
      <Handle
        type="target"
        position={Position.Left}
        className={`!w-2 !h-2 !border-2 !border-tsushin-deep`}
        style={{ backgroundColor: catConfig.color.includes('blue') ? '#60A5FA' : catConfig.color.includes('orange') ? '#FB923C' : catConfig.color.includes('red') ? '#F87171' : catConfig.color.includes('purple') ? '#A78BFA' : catConfig.color.includes('green') ? '#4ADE80' : catConfig.color.includes('pink') ? '#F472B6' : catConfig.color.includes('cyan') ? '#22D3EE' : catConfig.color.includes('amber') ? '#FBBF24' : '#2DD4BF' }}
      />

      {/* Source handle for expanded skills (connects to skills on the right in LR layout) */}
      {/* Always render the handle so React Flow can connect edges, but hide it visually when collapsed */}
      <Handle
        type="source"
        position={Position.Right}
        className={`!w-2 !h-2 !border-2 !border-tsushin-deep ${!data.isExpanded ? '!opacity-0' : ''}`}
        style={{
          backgroundColor: catConfig.color.includes('blue') ? '#60A5FA' : catConfig.color.includes('orange') ? '#FB923C' : catConfig.color.includes('red') ? '#F87171' : catConfig.color.includes('purple') ? '#A78BFA' : catConfig.color.includes('green') ? '#4ADE80' : catConfig.color.includes('pink') ? '#F472B6' : catConfig.color.includes('cyan') ? '#22D3EE' : catConfig.color.includes('amber') ? '#FBBF24' : '#2DD4BF',
          visibility: data.isExpanded ? 'visible' : 'hidden'
        }}
      />

      <div className="flex items-center gap-2">
        {/* Category Icon */}
        <div className={`flex-shrink-0 ${catConfig.color}`}>
          {catConfig.icon}
        </div>

        {/* Category Info */}
        <div className="flex flex-col min-w-0 flex-1">
          <div className="text-xs font-medium text-white">
            {data.categoryDisplayName || catConfig.displayName}
          </div>
          <div className="flex items-center gap-1 text-[10px]">
            <span className={`px-1.5 py-0.5 rounded ${catConfig.bgColor} ${catConfig.color}`}>
              {data.skillCount} skill{data.skillCount !== 1 ? 's' : ''}
            </span>
          </div>
        </div>

        {/* Expand/Collapse button */}
        {data.onExpand && data.onCollapse && (
          <button
            onClick={handleExpandClick}
            aria-label={data.isExpanded ? `Collapse ${data.categoryDisplayName} skills` : `Expand ${data.skillCount} ${data.categoryDisplayName} skills`}
            aria-expanded={data.isExpanded}
            className={`
              p-1 rounded transition-colors
              ${data.isExpanded
                ? `${catConfig.bgColor} ${catConfig.color}`
                : 'bg-tsushin-surface/50 text-tsushin-slate hover:text-white'
              }
            `}
          >
            <svg
              className={`w-3 h-3 transition-transform ${data.isExpanded ? 'rotate-180' : ''}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        )}
      </div>
    </div>
  )
}

export default memo(SkillCategoryNode)
