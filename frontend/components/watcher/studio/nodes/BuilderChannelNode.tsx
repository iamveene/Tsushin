'use client'
import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import type { BuilderChannelData } from '../types'

const CHANNEL_CONFIG: Record<string, { color: string; bgColor: string; label: string; nodeClass: string }> = {
  whatsapp: { color: 'text-green-400', bgColor: 'bg-green-500/20', label: 'WhatsApp', nodeClass: 'builder-node-channel-whatsapp' },
  telegram: { color: 'text-blue-400', bgColor: 'bg-blue-500/20', label: 'Telegram', nodeClass: 'builder-node-channel-telegram' },
  playground: { color: 'text-indigo-400', bgColor: 'bg-indigo-500/20', label: 'Playground', nodeClass: 'builder-node-channel-playground' },
  phone: { color: 'text-yellow-400', bgColor: 'bg-yellow-500/20', label: 'Phone', nodeClass: 'builder-node-channel-default' },
  discord: { color: 'text-violet-400', bgColor: 'bg-violet-500/20', label: 'Discord', nodeClass: 'builder-node-channel-default' },
  email: { color: 'text-orange-400', bgColor: 'bg-orange-500/20', label: 'Email', nodeClass: 'builder-node-channel-default' },
  sms: { color: 'text-emerald-400', bgColor: 'bg-emerald-500/20', label: 'SMS', nodeClass: 'builder-node-channel-default' },
}

function BuilderChannelNode({ data, selected }: NodeProps) {
  const d = data as BuilderChannelData
  const config = CHANNEL_CONFIG[d.channelType] || CHANNEL_CONFIG.playground
  return (
    <div role="group" aria-label={`Channel: ${d.label}`}
      className={`builder-node ${config.nodeClass} px-4 py-3 rounded-xl border transition-all duration-200 ${selected ? 'border-cyan-400 shadow-glow-sm' : 'border-tsushin-border hover:border-tsushin-muted'} bg-tsushin-surface`}>
      <Handle type="target" position={Position.Top} className="!bg-cyan-400 !border-tsushin-surface !w-3 !h-3" />
      <div className="flex items-center gap-2.5">
        <div className={`w-8 h-8 rounded-lg ${config.bgColor} flex items-center justify-center flex-shrink-0`}>
          <svg className={`w-4 h-4 ${config.color}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z" />
          </svg>
        </div>
        <div className="min-w-0">
          <p className="text-white text-sm font-medium">{config.label}</p>
          {d.phoneNumber && <p className="text-tsushin-muted text-xs">{d.phoneNumber}</p>}
          {d.botUsername && <p className="text-tsushin-muted text-xs">@{d.botUsername}</p>}
          {d.status && <span className={`text-2xs ${d.status === 'running' || d.status === 'active' ? 'text-green-400' : 'text-gray-500'}`}>{d.status}</span>}
        </div>
      </div>
    </div>
  )
}
export default memo(BuilderChannelNode)
