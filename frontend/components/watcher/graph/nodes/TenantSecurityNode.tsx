'use client'

/**
 * TenantSecurityNode - Root node for security hierarchy graph
 * Phase F (v1.6.0): Displays tenant with assigned Sentinel security profile
 */

import { memo, useState } from 'react'
import { NodeProps, Handle, Position } from '@xyflow/react'
import { TenantSecurityNodeData, SecurityDetectionMode } from '../types'

// Detection mode visual config
const modeConfig: Record<SecurityDetectionMode, { label: string; bgColor: string; textColor: string; borderColor: string }> = {
  block: {
    label: 'Block',
    bgColor: 'bg-red-500/20',
    textColor: 'text-red-400',
    borderColor: 'border-red-500/40',
  },
  detect_only: {
    label: 'Detect Only',
    bgColor: 'bg-amber-500/20',
    textColor: 'text-amber-400',
    borderColor: 'border-amber-500/40',
  },
  off: {
    label: 'Off',
    bgColor: 'bg-gray-500/20',
    textColor: 'text-gray-400',
    borderColor: 'border-gray-500/40',
  },
}

// Aggressiveness level display
function AggressivenessBar({ level }: { level: number }) {
  return (
    <div className="flex items-center gap-0.5" title={`Aggressiveness: ${level}`}>
      {[1, 2, 3].map((i) => (
        <div
          key={i}
          className={`w-1.5 h-3 rounded-sm ${
            i <= level ? 'bg-red-400' : 'bg-tsushin-border'
          }`}
        />
      ))}
    </div>
  )
}

function TenantSecurityNode(props: NodeProps<TenantSecurityNodeData>) {
  const { data, selected } = props
  const [showTooltip, setShowTooltip] = useState(false)

  const mode = modeConfig[data.detectionMode]
  const profileName = data.effectiveProfile?.name || data.profile?.name || 'No Profile'

  return (
    <div
      className={`
        relative px-5 py-4 rounded-xl border-2 min-w-[240px]
        transition-all duration-200
        ${selected
          ? 'border-tsushin-indigo bg-tsushin-surface shadow-lg shadow-tsushin-indigo/20'
          : `${mode.borderColor} bg-tsushin-deep hover:border-tsushin-border-hover`
        }
        ${!data.isEnabled ? 'opacity-60' : ''}
      `}
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      {/* Source handle only (root node — no target) */}
      <Handle
        type="source"
        position={Position.Bottom}
        className="!bg-tsushin-indigo !w-2.5 !h-2.5 !border-2 !border-tsushin-deep"
      />

      <div className="flex items-center gap-3">
        {/* Shield icon */}
        <div className={`w-10 h-10 rounded-lg ${mode.bgColor} flex items-center justify-center shrink-0`}>
          <svg className={`w-5 h-5 ${mode.textColor}`} viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2L3 7v5c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V7l-9-5zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12.99H5V8.26l7-3.89v8.62z" />
          </svg>
        </div>

        <div className="flex flex-col min-w-0 flex-1">
          {/* Tenant label */}
          <div className="text-[10px] uppercase tracking-wider text-tsushin-slate font-medium">
            Tenant
          </div>
          <div className="font-semibold text-white text-sm truncate">
            {data.tenantName}
          </div>

          {/* Profile + mode badges */}
          <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
            <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${mode.bgColor} ${mode.textColor}`}>
              {profileName}
            </span>
            <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${mode.bgColor} ${mode.textColor}`}>
              {mode.label}
            </span>
            <AggressivenessBar level={data.aggressivenessLevel} />
          </div>
        </div>
      </div>

      {/* Hover tooltip */}
      {showTooltip && (
        <div className="absolute left-full ml-2 top-0 z-50 bg-tsushin-deep border border-tsushin-border rounded-lg p-3 shadow-xl min-w-[200px] pointer-events-none">
          <div className="text-xs space-y-1.5">
            <div className="flex justify-between gap-4">
              <span className="text-tsushin-slate">Profile:</span>
              <span className="text-white font-medium">{profileName}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-tsushin-slate">Mode:</span>
              <span className={`font-medium ${mode.textColor}`}>{mode.label}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-tsushin-slate">Aggressiveness:</span>
              <span className="text-white font-medium">{data.aggressivenessLevel}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-tsushin-slate">Sentinel:</span>
              <span className={`font-medium ${data.isEnabled ? 'text-green-400' : 'text-red-400'}`}>
                {data.isEnabled ? 'Enabled' : 'Disabled'}
              </span>
            </div>
            {data.effectiveProfile?.source && (
              <div className="flex justify-between gap-4">
                <span className="text-tsushin-slate">Source:</span>
                <span className="text-tsushin-indigo font-medium capitalize">{data.effectiveProfile.source}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default memo(TenantSecurityNode)
