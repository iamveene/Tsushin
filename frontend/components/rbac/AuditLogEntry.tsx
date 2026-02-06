/**
 * Audit Log Entry Component
 * Displays a single audit log entry
 */

import React from 'react'
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
} from '@/components/ui/icons'
import type { IconProps } from '@/components/ui/icons'

interface AuditLogEntryProps {
  action: string
  user: string
  resource?: string
  timestamp: string
  ipAddress?: string
  details?: string
}

const actionIcons: Record<string, React.FC<IconProps>> = {
  'user.invited': InboxIcon,
  'user.removed': BanIcon,
  'user.role_changed': RefreshIcon,
  'agent.created': BotIcon,
  'agent.deleted': TrashIcon,
  'settings.updated': SettingsIcon,
  'billing.updated': CreditCardIcon,
  'login': LogInIcon,
  'logout': LogOutIcon,
}

const actionColors: Record<string, string> = {
  'user.invited': 'text-blue-600 dark:text-blue-400',
  'user.removed': 'text-red-600 dark:text-red-400',
  'user.role_changed': 'text-yellow-600 dark:text-yellow-400',
  'agent.created': 'text-green-600 dark:text-green-400',
  'agent.deleted': 'text-red-600 dark:text-red-400',
  'settings.updated': 'text-purple-600 dark:text-purple-400',
  'billing.updated': 'text-orange-600 dark:text-orange-400',
  'login': 'text-green-600 dark:text-green-400',
  'logout': 'text-gray-600 dark:text-gray-400',
}

export default function AuditLogEntry({
  action,
  user,
  resource,
  timestamp,
  ipAddress,
  details,
}: AuditLogEntryProps) {
  const Icon = actionIcons[action] || DocumentIcon
  const colorClass = actionColors[action] || 'text-gray-600 dark:text-gray-400'

  return (
    <div className="flex items-start space-x-4 p-4 hover:bg-gray-50 dark:hover:bg-gray-900/50 rounded-lg transition-colors">
      <Icon size={20} className={colorClass} />
      <div className="flex-1">
        <div className="flex items-center space-x-2 mb-1">
          <span className={`text-sm font-medium ${colorClass}`}>
            {action.replace(/\./g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
          </span>
          {resource && (
            <span className="text-sm text-gray-600 dark:text-gray-400">
              · {resource}
            </span>
          )}
        </div>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          <strong>{user}</strong> {details || action.split('.')[1]}
        </p>
        <div className="flex items-center space-x-3 mt-2 text-xs text-gray-500 dark:text-gray-400">
          <span className="inline-flex items-center gap-1"><ClockIcon size={12} /> {timestamp}</span>
          {ipAddress && <span className="inline-flex items-center gap-1"><GlobeIcon size={12} /> {ipAddress}</span>}
        </div>
      </div>
    </div>
  )
}
