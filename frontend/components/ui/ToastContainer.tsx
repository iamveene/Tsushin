'use client'

import React, { useEffect, useState } from 'react'
import { useToast, type Toast, type ToastType } from '@/contexts/ToastContext'

const typeConfig: Record<ToastType, { accentColor: string; icon: string }> = {
  success: { accentColor: 'bg-tsushin-success', icon: '\u2713' },
  error: { accentColor: 'bg-tsushin-vermilion', icon: '\u2717' },
  warning: { accentColor: 'bg-tsushin-warning', icon: '\u26A0' },
  info: { accentColor: 'bg-tsushin-indigo', icon: '\u2139' },
}

function ToastItem({ toast, onRemove }: { toast: Toast; onRemove: (id: string) => void }) {
  const [exiting, setExiting] = useState(false)
  const config = typeConfig[toast.type]

  const handleClose = () => {
    setExiting(true)
    setTimeout(() => onRemove(toast.id), 200)
  }

  // Trigger exit animation slightly before auto-dismiss
  useEffect(() => {
    const exitDelay = Math.max(toast.duration - 300, 0)
    const timer = setTimeout(() => setExiting(true), exitDelay)
    return () => clearTimeout(timer)
  }, [toast.duration])

  return (
    <div
      className={`
        flex overflow-hidden rounded-xl
        bg-tsushin-elevated border border-tsushin-border
        shadow-elevated
        transition-all duration-200 ease-out
        ${exiting ? 'opacity-0 translate-x-4' : 'animate-slide-in-right opacity-100'}
      `}
      role="alert"
    >
      {/* Color accent bar */}
      <div className={`w-1 shrink-0 ${config.accentColor}`} />

      <div className="flex items-start gap-3 p-4 flex-1 min-w-0">
        {/* Icon */}
        <span className="text-sm mt-0.5 shrink-0">{config.icon}</span>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-white leading-tight">{toast.title}</p>
          {toast.message && (
            <p className="text-xs text-tsushin-slate mt-1 leading-relaxed">{toast.message}</p>
          )}
        </div>

        {/* Close button */}
        <button
          onClick={handleClose}
          className="shrink-0 text-tsushin-slate hover:text-white transition-colors ml-2 mt-0.5"
          aria-label="Dismiss"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M11 3L3 11M3 3L11 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </button>
      </div>
    </div>
  )
}

export default function ToastContainer() {
  const { toasts, removeToast } = useToast()

  if (toasts.length === 0) return null

  return (
    <div className="fixed bottom-4 right-4 z-[80] flex flex-col gap-2 max-w-sm w-full pointer-events-none">
      {toasts.map(toast => (
        <div key={toast.id} className="pointer-events-auto">
          <ToastItem toast={toast} onRemove={removeToast} />
        </div>
      ))}
    </div>
  )
}
