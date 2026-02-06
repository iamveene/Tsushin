'use client'

/**
 * SkillProviderNode - Displays an available provider for a skill
 * Phase 9: Shows providers like "Google Flights", "Brave", "Gmail" as children of skills
 */

import { memo } from 'react'
import { NodeProps, Handle, Position } from '@xyflow/react'
import { SkillProviderNodeData } from '../types'

// Provider configuration with colors and icons based on provider type
const providerConfig: Record<string, { color: string; bgColor: string; borderColor: string; icon: JSX.Element }> = {
  // Google Flights
  'google_flights': {
    color: 'text-cyan-400',
    bgColor: 'bg-cyan-500/10',
    borderColor: 'border-cyan-500/30',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
      </svg>
    ),
  },
  // Amadeus
  'amadeus': {
    color: 'text-blue-400',
    bgColor: 'bg-blue-500/10',
    borderColor: 'border-blue-500/30',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 013 12c0-1.605.42-3.113 1.157-4.418" />
      </svg>
    ),
  },
  // Google Calendar
  'google_calendar': {
    color: 'text-blue-400',
    bgColor: 'bg-blue-500/10',
    borderColor: 'border-blue-500/30',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" />
      </svg>
    ),
  },
  // Asana
  'asana': {
    color: 'text-orange-400',
    bgColor: 'bg-orange-500/10',
    borderColor: 'border-orange-500/30',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
  // Flows (Built-in)
  'flows': {
    color: 'text-purple-400',
    bgColor: 'bg-purple-500/10',
    borderColor: 'border-purple-500/30',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5" />
      </svg>
    ),
  },
  // Gmail
  'gmail': {
    color: 'text-red-400',
    bgColor: 'bg-red-500/10',
    borderColor: 'border-red-500/30',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
      </svg>
    ),
  },
  // Brave (Web Search)
  'brave': {
    color: 'text-orange-400',
    bgColor: 'bg-orange-500/10',
    borderColor: 'border-orange-500/30',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
      </svg>
    ),
  },
  // Google (Web Search)
  'google': {
    color: 'text-blue-400',
    bgColor: 'bg-blue-500/10',
    borderColor: 'border-blue-500/30',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
      </svg>
    ),
  },
  // SerpAPI
  'serpapi': {
    color: 'text-green-400',
    bgColor: 'bg-green-500/10',
    borderColor: 'border-green-500/30',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
      </svg>
    ),
  },
  // Default fallback
  'default': {
    color: 'text-slate-400',
    bgColor: 'bg-slate-500/10',
    borderColor: 'border-slate-500/30',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244" />
      </svg>
    ),
  },
}

function getProviderConfig(providerType: string) {
  return providerConfig[providerType.toLowerCase()] || providerConfig['default']
}

function SkillProviderNode(props: NodeProps<SkillProviderNodeData>) {
  const { data, selected } = props

  const config = getProviderConfig(data.providerType)

  // Phase 8: Real-time activity glow
  const isActive = data.isActive ?? false
  const isFading = data.isFading ?? false

  return (
    <div
      className={`
        relative px-3 py-2 rounded-lg border min-w-[120px]
        transition-all duration-200
        ${selected
          ? `${config.borderColor} ${config.bgColor} shadow-lg`
          : `border-tsushin-border bg-tsushin-surface hover:${config.borderColor}`
        }
        ${data.isConfigured ? 'ring-1 ring-green-500/50' : ''}
        ${isActive && !isFading ? 'skill-provider-node-active' : isFading ? 'skill-provider-node-fading' : ''}
      `}
      title={data.providerDescription}
    >
      {/* Connection handle - target (connects from skill on the left in LR layout) */}
      <Handle
        type="target"
        position={Position.Left}
        className="!w-2 !h-2 !border-2 !border-tsushin-deep"
        style={{ backgroundColor: config.color.includes('cyan') ? '#22D3EE' : '#A78BFA' }}
      />

      <div className="flex items-center gap-2">
        {/* Provider Icon */}
        <div className={`flex-shrink-0 ${config.color}`}>
          {config.icon}
        </div>

        {/* Provider Info */}
        <div className="flex flex-col min-w-0">
          <div className="text-xs font-medium text-white truncate max-w-[90px]" title={data.providerName}>
            {data.providerName}
          </div>
          <div className="flex items-center gap-1 text-[10px]">
            {data.isConfigured ? (
              <span className="px-1.5 py-0.5 rounded bg-green-500/20 text-green-400">
                Active
              </span>
            ) : data.requiresIntegration ? (
              <span className="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400">
                Setup Required
              </span>
            ) : (
              <span className={`px-1.5 py-0.5 rounded ${config.bgColor} ${config.color}`}>
                Available
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default memo(SkillProviderNode)
