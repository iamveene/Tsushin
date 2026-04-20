'use client'

/**
 * MiniStreamingMessage — inline pending indicator while Playground Mini
 * awaits a sync HTTP response. Renders a trio of pulsing dots inside an
 * assistant-style bubble so the user knows the agent is thinking.
 */

import React from 'react'
import { BotIcon } from '@/components/ui/icons'

export default function MiniStreamingMessage() {
  return (
    <div className="flex items-start gap-2 animate-fade-in" aria-label="Agent is thinking">
      <div className="flex-shrink-0 w-6 h-6 rounded-md bg-tsushin-elevated border border-tsushin-border flex items-center justify-center text-tsushin-accent">
        <BotIcon size={14} />
      </div>
      <div className="flex items-center gap-1 px-3 py-2 rounded-lg bg-tsushin-elevated border border-tsushin-border text-tsushin-slate">
        <span className="w-1.5 h-1.5 rounded-full bg-tsushin-accent animate-pulse" style={{ animationDelay: '0ms' }} />
        <span className="w-1.5 h-1.5 rounded-full bg-tsushin-accent animate-pulse" style={{ animationDelay: '150ms' }} />
        <span className="w-1.5 h-1.5 rounded-full bg-tsushin-accent animate-pulse" style={{ animationDelay: '300ms' }} />
      </div>
    </div>
  )
}
