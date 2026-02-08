'use client'

import { memo, useState, useCallback, useRef, lazy, Suspense } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import type { BuilderAgentData } from '../types'
import { AgentAvatarIcon } from '../avatars/AgentAvatars'

const AvatarPicker = lazy(() => import('../avatars/AvatarPicker').then(m => ({ default: m.AvatarPicker })))

function BuilderAgentNode({ data, selected }: NodeProps) {
  const d = data as BuilderAgentData
  const [showPicker, setShowPicker] = useState(false)
  const [pickerAnchor, setPickerAnchor] = useState({ x: 0, y: 0 })
  const avatarRef = useRef<HTMLButtonElement>(null)

  const handleAvatarClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    if (!d.onAvatarChange) return
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    setPickerAnchor({ x: rect.right + 8, y: rect.top })
    setShowPicker(true)
  }, [d.onAvatarChange])

  const handleAvatarSelect = useCallback((slug: string | null) => {
    d.onAvatarChange?.(slug)
  }, [d.onAvatarChange])

  return (
    <div role="group" aria-label={`Agent: ${d.name}`}
      className={`builder-node builder-node-agent px-6 py-5 rounded-xl border-2 transition-all duration-200 ${selected ? 'border-tsushin-indigo shadow-glow-sm' : 'border-tsushin-indigo/40 hover:border-tsushin-indigo/70'} bg-tsushin-surface`}>
      <Handle type="source" position={Position.Bottom} className="!bg-tsushin-indigo !border-tsushin-surface !w-3 !h-3" />
      <div className="flex items-center gap-4 mb-3">
        <button ref={avatarRef} onClick={handleAvatarClick} className="group relative cursor-pointer" title="Click to change avatar">
          <AgentAvatarIcon slug={d.avatar} size="lg" />
          <div className="absolute inset-0 rounded-lg bg-white/10 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
            <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L6.832 19.82a4.5 4.5 0 01-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 011.13-1.897L16.863 4.487z" />
            </svg>
          </div>
        </button>
        <div className="min-w-0">
          <h3 className="text-white font-semibold text-sm truncate max-w-[180px]">{d.name}</h3>
          <p className="text-tsushin-muted text-xs truncate max-w-[180px]">{d.modelProvider}/{d.modelName}</p>
        </div>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-2xs font-medium ${d.isActive ? 'bg-green-500/20 text-green-300' : 'bg-gray-500/20 text-gray-400'}`}>
          <span className={`w-1.5 h-1.5 rounded-full ${d.isActive ? 'bg-green-400' : 'bg-gray-500'}`} />
          {d.isActive ? 'Active' : 'Inactive'}
        </span>
        {d.isDefault && <span className="inline-flex items-center px-2 py-0.5 rounded-full text-2xs font-medium bg-tsushin-indigo/20 text-tsushin-indigo">Default</span>}
        {d.enabledChannels.length > 0 && <span className="inline-flex items-center px-2 py-0.5 rounded-full text-2xs font-medium bg-cyan-500/20 text-cyan-300">{d.enabledChannels.length} ch</span>}
        {d.personaName && <span className="inline-flex items-center px-2 py-0.5 rounded-full text-2xs font-medium bg-purple-500/20 text-purple-300 truncate max-w-[100px]">{d.personaName}</span>}
      </div>
      {showPicker && d.onAvatarChange && (
        <Suspense fallback={null}>
          <AvatarPicker selected={d.avatar} onSelect={handleAvatarSelect} anchor={pickerAnchor} onClose={() => setShowPicker(false)} />
        </Suspense>
      )}
    </div>
  )
}

export default memo(BuilderAgentNode)
