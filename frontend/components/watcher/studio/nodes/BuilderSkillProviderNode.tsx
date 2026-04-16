'use client'

import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import type { BuilderSkillProviderData } from '../types'

const providerColors: Record<string, { text: string; bg: string; border: string }> = {
  google_flights: { text: 'text-cyan-400', bg: 'bg-cyan-500/10', border: 'border-cyan-500/30' },
  amadeus: { text: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/30' },
  google_calendar: { text: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/30' },
  asana: { text: 'text-orange-400', bg: 'bg-orange-500/10', border: 'border-orange-500/30' },
  flows: { text: 'text-purple-400', bg: 'bg-purple-500/10', border: 'border-purple-500/30' },
  gmail: { text: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/30' },
  brave: { text: 'text-orange-400', bg: 'bg-orange-500/10', border: 'border-orange-500/30' },
  google: { text: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/30' },
  serpapi: { text: 'text-green-400', bg: 'bg-green-500/10', border: 'border-green-500/30' },
  default: { text: 'text-slate-400', bg: 'bg-slate-500/10', border: 'border-slate-500/30' },
}

function getColors(providerType: string) {
  return providerColors[providerType.toLowerCase()] || providerColors.default
}

function BuilderSkillProviderNode({ data, selected }: NodeProps) {
  const d = data as BuilderSkillProviderData
  const colors = getColors(d.providerType)

  return (
    <div className={`builder-node px-3 py-2 rounded-lg border transition-all duration-200 min-w-[120px] ${selected ? `${colors.border} ${colors.bg} shadow-lg` : `border-tsushin-border bg-tsushin-surface hover:${colors.border}`} ${d.isConfigured ? 'ring-1 ring-green-500/40' : ''}`}>
      <Handle type="target" position={Position.Top} className="!w-2 !h-2 !border-2 !border-tsushin-deep" style={{ backgroundColor: '#A78BFA' }} />
      <div className="flex items-center gap-2">
        <div className={`flex-shrink-0 ${colors.text}`}>
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244" />
          </svg>
        </div>
        <div className="min-w-0">
          <p className="text-white text-xs font-medium truncate max-w-[90px]">{d.providerName}</p>
          <span className={`text-2xs ${d.isConfigured ? 'text-green-400' : 'text-tsushin-muted'}`}>
            {d.isConfigured ? 'Active' : d.requiresIntegration ? 'Setup Needed' : 'Available'}
          </span>
        </div>
      </div>
    </div>
  )
}

export default memo(BuilderSkillProviderNode)
