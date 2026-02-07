'use client'
import { useState, ReactNode } from 'react'

interface PaletteCategoryProps {
  title: string; icon: ReactNode; count: number; attachedCount: number; cardinality: string; children: ReactNode; defaultOpen?: boolean
}

export default function PaletteCategory({ title, icon, count, attachedCount, cardinality, children, defaultOpen = false }: PaletteCategoryProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen)
  return (
    <div className="border-b border-tsushin-border/30 last:border-b-0">
      <button onClick={() => setIsOpen(!isOpen)} className="w-full flex items-center gap-2 px-3 py-2.5 hover:bg-tsushin-surface/50 transition-colors">
        <svg className={`w-3.5 h-3.5 text-tsushin-muted flex-shrink-0 transition-transform duration-200 ${isOpen ? 'rotate-90' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
        <span className="flex-shrink-0">{icon}</span>
        <span className="text-sm text-white font-medium flex-1 text-left">{title}</span>
        <span className="text-2xs text-tsushin-muted flex-shrink-0">{cardinality}</span>
        <span className="text-2xs bg-tsushin-surface px-1.5 py-0.5 rounded text-tsushin-slate flex-shrink-0">{attachedCount}/{count}</span>
      </button>
      {isOpen && <div className="pb-1">{count === 0 ? <p className="px-3 py-2 text-2xs text-tsushin-muted italic">No items available</p> : children}</div>}
    </div>
  )
}
