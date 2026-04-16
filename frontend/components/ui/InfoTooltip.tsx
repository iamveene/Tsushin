'use client'

import { useState, useRef, useEffect } from 'react'

interface InfoTooltipProps {
  text: string
  title?: string
  position?: 'top' | 'bottom' | 'left' | 'right'
  className?: string
}

export default function InfoTooltip({
  text,
  title,
  position = 'top',
  className = '',
}: InfoTooltipProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    const esc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('mousedown', handler)
      document.removeEventListener('keydown', esc)
    }
  }, [open])

  const positionClasses: Record<string, string> = {
    top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
    bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
    left: 'right-full top-1/2 -translate-y-1/2 mr-2',
    right: 'left-full top-1/2 -translate-y-1/2 ml-2',
  }

  return (
    <div ref={ref} className={`relative inline-flex items-center ${className}`}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-4 h-4 rounded-full border border-tsushin-slate/50 text-tsushin-slate hover:text-teal-400 hover:border-teal-400 flex items-center justify-center text-[10px] font-bold transition-colors"
        aria-label="More info"
      >
        i
      </button>
      {open && (
        <div
          className={`absolute z-50 w-64 p-3 bg-tsushin-elevated border border-tsushin-border rounded-lg shadow-elevated text-sm ${positionClasses[position]}`}
        >
          {title && (
            <p className="font-semibold text-white mb-1">{title}</p>
          )}
          <p className="text-tsushin-slate leading-relaxed">{text}</p>
        </div>
      )}
    </div>
  )
}
