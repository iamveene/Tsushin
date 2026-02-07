'use client'

/**
 * SkillSecurityNode - Compact leaf node for security hierarchy graph
 * Phase F (v1.6.0): Shows skill with assigned/effective Sentinel profile
 */

import { memo, useState } from 'react'
import { NodeProps, Handle, Position } from '@xyflow/react'
import { SkillSecurityNodeData, SecurityDetectionMode } from '../types'

const modeColors: Record<SecurityDetectionMode, { bg: string; text: string }> = {
  block: { bg: 'bg-red-500/20', text: 'text-red-400' },
  detect_only: { bg: 'bg-amber-500/20', text: 'text-amber-400' },
  off: { bg: 'bg-gray-500/20', text: 'text-gray-400' },
}

// Skill type icons (matching the existing SkillNode pattern)
const skillIcons: Record<string, JSX.Element> = {
  shell: (
    <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="m6.75 7.5 3 2.25-3 2.25m4.5 0h3m-9 8.25h13.5A2.25 2.25 0 0 0 21 18V6a2.25 2.25 0 0 0-2.25-2.25H5.25A2.25 2.25 0 0 0 3 6v12a2.25 2.25 0 0 0 2.25 2.25Z" />
    </svg>
  ),
  web_search: (
    <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
    </svg>
  ),
  browser_automation: (
    <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9.004 9.004 0 0 0 8.716-6.747M12 21a9.004 9.004 0 0 1-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 0 1 7.843 4.582M12 3a8.997 8.997 0 0 0-7.843 4.582" />
    </svg>
  ),
}

const defaultSkillIcon = (
  <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path strokeLinecap="round" strokeLinejoin="round" d="M11.42 15.17 17.25 21A2.652 2.652 0 0 0 21 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 1 1-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 0 0 4.486-6.336l-3.276 3.277a3.004 3.004 0 0 1-2.25-2.25l3.276-3.276a4.5 4.5 0 0 0-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085" />
  </svg>
)

function SkillSecurityNode(props: NodeProps<SkillSecurityNodeData>) {
  const { data, selected } = props
  const [showTooltip, setShowTooltip] = useState(false)

  const hasExplicitProfile = data.profile !== null
  const effectiveName = data.effectiveProfile?.name || 'None'
  const effectiveSource = data.effectiveProfile?.source || 'agent'
  const mode = modeColors[data.detectionMode]
  const icon = skillIcons[data.skillType] || defaultSkillIcon

  return (
    <div
      className={`
        relative px-3 py-2 rounded-lg border min-w-[160px]
        transition-all duration-200
        ${selected
          ? 'border-tsushin-indigo bg-tsushin-surface shadow-lg shadow-tsushin-indigo/20'
          : hasExplicitProfile
            ? 'border-purple-500/40 bg-tsushin-deep hover:border-purple-500/60'
            : 'border-dashed border-tsushin-border bg-tsushin-deep hover:border-tsushin-border-hover'
        }
        ${!data.isEnabled ? 'opacity-50' : ''}
      `}
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      {/* Target handle (top - from agent) */}
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-tsushin-accent !w-2 !h-2 !border-2 !border-tsushin-deep"
      />

      <div className="flex items-center gap-2">
        {/* Skill icon */}
        <div className={`w-6 h-6 rounded flex items-center justify-center shrink-0 ${mode.bg}`}>
          <span className={mode.text}>{icon}</span>
        </div>

        <div className="flex flex-col min-w-0 flex-1">
          <div className="font-medium text-white text-xs truncate max-w-[120px]">
            {data.skillName}
          </div>
          <div className="flex items-center gap-1 mt-0.5">
            <span className={`px-1 py-0 rounded text-[9px] font-medium ${mode.bg} ${mode.text}`}>
              {effectiveName}
            </span>
            {hasExplicitProfile ? (
              <span className="px-1 py-0 rounded text-[9px] font-medium bg-purple-500/20 text-purple-400">
                Custom
              </span>
            ) : (
              <span className="px-1 py-0 rounded text-[9px] font-medium bg-gray-500/15 text-tsushin-slate">
                Inherited
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Hover tooltip */}
      {showTooltip && (
        <div className="absolute left-full ml-2 top-0 z-50 bg-tsushin-deep border border-tsushin-border rounded-lg p-2.5 shadow-xl min-w-[170px] pointer-events-none">
          <div className="text-xs space-y-1">
            <div className="flex justify-between gap-3">
              <span className="text-tsushin-slate">Skill:</span>
              <span className="text-white font-medium">{data.skillName}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-tsushin-slate">Type:</span>
              <span className="text-tsushin-slate">{data.skillType}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-tsushin-slate">Profile:</span>
              <span className="text-white font-medium">{effectiveName}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-tsushin-slate">Source:</span>
              <span className="text-tsushin-indigo font-medium capitalize">{effectiveSource}</span>
            </div>
            {hasExplicitProfile && data.profile && (
              <div className="flex justify-between gap-3">
                <span className="text-tsushin-slate">Assigned:</span>
                <span className="text-purple-400 font-medium">{data.profile.name}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default memo(SkillSecurityNode)
