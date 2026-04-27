/**
 * Audit Log Entry Component — v0.6.0 Enhanced
 * Displays a single audit event with severity, channel, and expandable details.
 */

'use client'

import React, { useState } from 'react'
import {
  InboxIcon,
  BanIcon,
  RefreshIcon,
  BotIcon,
  TrashIcon,
  SettingsIcon,
  CreditCardIcon,
  LogInIcon,
  LogOutIcon,
  DocumentIcon,
  ClockIcon,
  GlobeIcon,
  KeyIcon,
  ShieldIcon,
  ShieldCheckIcon,
  TerminalIcon,
  UserIcon,
  ServerIcon,
} from '@/components/ui/icons'
import type { IconProps } from '@/components/ui/icons'

interface AuditLogEntryProps {
  action: string
  user: string
  resource?: string
  timestamp: string
  ipAddress?: string
  details?: string
  severity?: string
  channel?: string
  onFilterAction?: (action: string) => void
}

// Map action prefixes to icons
const getActionIcon = (action: string): React.FC<IconProps> => {
  const prefix = action.split('.')[0]
  const full = action

  const iconMap: Record<string, React.FC<IconProps>> = {
    'auth.login': LogInIcon,
    'auth.logout': LogOutIcon,
    'auth.failed_login': BanIcon,
    'auth.password_change': KeyIcon,
    'auth.password_reset': KeyIcon,
    'agent.create': BotIcon,
    'agent.update': RefreshIcon,
    'agent.delete': TrashIcon,
    'agent.skill_change': BotIcon,
    'flow.create': DocumentIcon,
    'flow.update': RefreshIcon,
    'flow.delete': TrashIcon,
    'flow.execute': DocumentIcon,
    'contact.create': UserIcon,
    'contact.update': RefreshIcon,
    'contact.delete': TrashIcon,
    'settings.update': SettingsIcon,
    'security.sentinel_block': ShieldIcon,
    'security.permission_denied': BanIcon,
    'shell.command_queued': TerminalIcon,
    'shell.command_blocked': BanIcon,
    'shell.command_pending_approval': ShieldIcon,
    'shell.approval_requested': ShieldIcon,
    'shell.approved': ShieldCheckIcon,
    'shell.rejected': BanIcon,
    'shell.expired': ClockIcon,
    'shell.beacon_registered': ServerIcon,
    'api_client.create': KeyIcon,
    'api_client.rotate': RefreshIcon,
    'api_client.revoke': TrashIcon,
    'skill.create': DocumentIcon,
    'skill.update': RefreshIcon,
    'skill.delete': TrashIcon,
    'skill.deploy': DocumentIcon,
    'mcp.create': GlobeIcon,
    'mcp.delete': TrashIcon,
    'mcp.connect': GlobeIcon,
    'mcp.disconnect': BanIcon,
    'team.invite': InboxIcon,
    'team.remove': BanIcon,
    'team.role_change': RefreshIcon,
    'billing.updated': CreditCardIcon,
  }

  if (iconMap[full]) return iconMap[full]

  const prefixMap: Record<string, React.FC<IconProps>> = {
    auth: LogInIcon,
    agent: BotIcon,
    flow: DocumentIcon,
    contact: UserIcon,
    settings: SettingsIcon,
    security: ShieldIcon,
    shell: TerminalIcon,
    api_client: KeyIcon,
    skill: DocumentIcon,
    mcp: GlobeIcon,
    team: InboxIcon,
    billing: CreditCardIcon,
  }

  return prefixMap[prefix] || DocumentIcon
}

// Map action prefixes to colors
const getActionColor = (action: string): string => {
  const prefix = action.split('.')[0]
  const suffix = action.split('.')[1]

  if (suffix === 'delete' || suffix === 'revoke' || suffix === 'remove' || action === 'auth.failed_login' || action === 'security.sentinel_block') {
    return 'text-red-400'
  }
  if (suffix === 'create' || suffix === 'invite' || action === 'auth.login' || suffix === 'connect') {
    return 'text-green-400'
  }
  if (suffix === 'update' || suffix === 'rotate' || suffix === 'role_change') {
    return 'text-amber-400'
  }
  if (prefix === 'shell') {
    if (suffix === 'approved' || suffix === 'command_queued') return 'text-teal-400'
    if (suffix === 'command_pending_approval' || suffix === 'approval_requested' || suffix === 'expired') return 'text-amber-400'
  }
  if (prefix === 'security') return 'text-red-400'
  if (prefix === 'auth') return 'text-blue-400'

  return 'text-tsushin-slate'
}

const severityDot: Record<string, string> = {
  info: 'bg-blue-400',
  warning: 'bg-amber-400',
  critical: 'bg-red-500',
}

const channelBadgeColor: Record<string, string> = {
  web: 'bg-blue-500/20 text-blue-300',
  api: 'bg-purple-500/20 text-purple-300',
  whatsapp: 'bg-green-500/20 text-green-300',
  telegram: 'bg-sky-500/20 text-sky-300',
  system: 'bg-gray-500/20 text-gray-300',
}

function formatTimestamp(ts: string): string {
  try {
    const d = new Date(ts)
    const now = new Date()
    const diff = now.getTime() - d.getTime()

    if (diff < 60000) return 'just now'
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`
    if (diff < 604800000) return `${Math.floor(diff / 86400000)}d ago`

    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch {
    return ts
  }
}

export default function AuditLogEntry({
  action,
  user,
  resource,
  timestamp,
  ipAddress,
  details,
  severity = 'info',
  channel,
  onFilterAction,
}: AuditLogEntryProps) {
  const [expanded, setExpanded] = useState(false)
  const Icon = getActionIcon(action)
  const colorClass = getActionColor(action)

  const actionLabel = action
    .replace(/\./g, ' ')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (l) => l.toUpperCase())

  return (
    <div className="flex items-start gap-3 px-4 py-3 hover:bg-white/[0.02] transition-colors">
      {/* Severity dot */}
      <div className="flex flex-col items-center gap-1 pt-1">
        <div className={`w-2 h-2 rounded-full ${severityDot[severity] || severityDot.info}`} title={severity} />
      </div>

      {/* Icon */}
      <div className="pt-0.5">
        <Icon size={16} className={colorClass} />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => onFilterAction?.(action)}
            className={`text-sm font-medium ${colorClass} hover:underline cursor-pointer`}
            title="Click to filter by this action"
          >
            {actionLabel}
          </button>
          {resource && (
            <span className="text-xs text-tsushin-slate truncate max-w-[200px]" title={resource}>
              {resource}
            </span>
          )}
          {channel && (
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${channelBadgeColor[channel] || channelBadgeColor.system}`}>
              {channel}
            </span>
          )}
        </div>

        <p className="text-sm text-white/80 mt-0.5">
          <span className="font-medium text-white">{user}</span>
          {details && !expanded && (
            <span className="text-tsushin-slate"> &mdash; </span>
          )}
          {details && !expanded && (
            <button
              onClick={() => setExpanded(true)}
              className="text-xs text-teal-400 hover:text-teal-300"
            >
              show details
            </button>
          )}
        </p>

        {/* Expanded details */}
        {expanded && details && (
          <div className="mt-2 bg-black/20 rounded-md p-2 relative">
            <button
              onClick={() => setExpanded(false)}
              className="absolute top-1 right-1 text-xs text-tsushin-slate hover:text-white"
            >
              hide
            </button>
            <pre className="text-xs text-tsushin-slate whitespace-pre-wrap break-all font-mono">
              {(() => {
                try {
                  return JSON.stringify(JSON.parse(details), null, 2)
                } catch {
                  return details
                }
              })()}
            </pre>
          </div>
        )}

        {/* Meta row */}
        <div className="flex items-center gap-3 mt-1 text-[11px] text-tsushin-slate/70">
          <span className="inline-flex items-center gap-1">
            <ClockIcon size={10} />
            {formatTimestamp(timestamp)}
          </span>
          {ipAddress && (
            <span className="inline-flex items-center gap-1">
              <GlobeIcon size={10} />
              {ipAddress}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
