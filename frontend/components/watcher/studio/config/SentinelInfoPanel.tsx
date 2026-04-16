'use client'

import type { BuilderSentinelData } from '../types'

interface SentinelInfoPanelProps {
  data: BuilderSentinelData
}

const modeBadgeStyles: Record<string, string> = {
  block: 'bg-red-500/20 text-red-300',
  warn_only: 'bg-yellow-500/20 text-yellow-300',
  detect_only: 'bg-blue-500/20 text-blue-300',
  off: 'bg-gray-500/20 text-gray-400',
}

export default function SentinelInfoPanel({ data }: SentinelInfoPanelProps) {
  return (
    <div className="space-y-4">
      <div className="config-field">
        <label>Profile Name</label>
        <p className="text-sm text-white">{data.name}</p>
      </div>

      <div className="config-field">
        <label>Detection Mode</label>
        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${modeBadgeStyles[data.mode] || modeBadgeStyles.off}`}>
          {data.mode.replace(/_/g, ' ')}
        </span>
      </div>

      {data.isSystem && (
        <div className="config-field">
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-500/20 text-purple-300">
            System Profile
          </span>
        </div>
      )}

      <div className="border-t border-tsushin-border pt-3">
        <a
          href="/agents?tab=security"
          className="inline-flex items-center gap-1.5 text-xs text-tsushin-indigo hover:text-tsushin-indigo/80 transition-colors"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
          </svg>
          Edit in Security
        </a>
      </div>
    </div>
  )
}
