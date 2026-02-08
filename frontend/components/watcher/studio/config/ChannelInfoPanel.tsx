'use client'

import type { BuilderChannelData } from '../types'

interface ChannelInfoPanelProps {
  data: BuilderChannelData
}

const channelIcons: Record<string, string> = {
  whatsapp: '#25D366',
  telegram: '#2AABEE',
  playground: '#6366F1',
  phone: '#10B981',
  discord: '#5865F2',
  email: '#EA4335',
  sms: '#F59E0B',
}

export default function ChannelInfoPanel({ data }: ChannelInfoPanelProps) {
  const color = channelIcons[data.channelType] || '#8B929E'

  return (
    <div className="space-y-4">
      <div className="config-field">
        <label>Channel Type</label>
        <div className="flex items-center gap-2 mt-1">
          <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
          <p className="text-sm text-white">{data.label}</p>
        </div>
      </div>

      {data.phoneNumber && (
        <div className="config-field">
          <label>Phone Number</label>
          <p className="text-sm text-tsushin-slate">{data.phoneNumber}</p>
        </div>
      )}

      {data.botUsername && (
        <div className="config-field">
          <label>Bot Username</label>
          <p className="text-sm text-tsushin-slate">@{data.botUsername}</p>
        </div>
      )}

      {data.status && (
        <div className="config-field">
          <label>Status</label>
          <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${data.status === 'connected' ? 'bg-green-500/20 text-green-300' : 'bg-yellow-500/20 text-yellow-300'}`}>
            {data.status}
          </span>
        </div>
      )}

      <div className="border-t border-tsushin-border pt-3">
        <p className="text-xs text-tsushin-muted">
          Channel configuration is managed in Agent Settings.
        </p>
      </div>
    </div>
  )
}
