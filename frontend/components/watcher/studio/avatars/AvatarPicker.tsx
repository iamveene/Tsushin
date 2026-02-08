'use client'

import { useState, useRef, useEffect, memo } from 'react'
import { AGENT_AVATARS, type AvatarDef } from './AgentAvatars'

interface AvatarPickerProps {
  selected: string | null | undefined
  onSelect: (slug: string | null) => void
  anchor: { x: number; y: number }
  onClose: () => void
}

function AvatarPickerInner({ selected, onSelect, anchor, onClose }: AvatarPickerProps) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('keydown', handleEscape)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleEscape)
    }
  }, [onClose])

  return (
    <div ref={ref} className="fixed z-[200] bg-tsushin-deep border border-tsushin-border rounded-xl shadow-2xl p-3 w-[280px] animate-fade-in"
      style={{ left: anchor.x, top: anchor.y }}
      onClick={(e) => e.stopPropagation()}>
      <div className="text-xs font-medium text-tsushin-slate mb-2">Choose Avatar</div>
      <div className="grid grid-cols-5 gap-1.5">
        {/* None option */}
        <button onClick={() => { onSelect(null); onClose() }}
          className={`w-full aspect-square rounded-lg flex items-center justify-center transition-all ${!selected ? 'ring-2 ring-tsushin-indigo bg-tsushin-indigo/20' : 'bg-tsushin-surface hover:bg-tsushin-surface/80'}`}
          title="Default icon">
          <svg className="w-5 h-5 text-tsushin-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" />
          </svg>
        </button>
        {AGENT_AVATARS.map(avatar => (
          <button key={avatar.slug} onClick={() => { onSelect(avatar.slug); onClose() }}
            className={`w-full aspect-square rounded-lg flex items-center justify-center transition-all p-1.5 ${selected === avatar.slug ? 'ring-2 ring-tsushin-indigo ' + avatar.color : 'bg-tsushin-surface hover:bg-tsushin-surface/80'}`}
            title={avatar.label}>
            {avatar.svg}
          </button>
        ))}
      </div>
    </div>
  )
}

export const AvatarPicker = memo(AvatarPickerInner)
