/**
 * Role Badge Component
 * Visual indicator for user roles
 */

import { ROLE_ICON_MAP } from '@/components/ui/icons'

interface RoleBadgeProps {
  role: string
  size?: 'sm' | 'md' | 'lg'
}

const roleConfig = {
  owner: {
    label: 'Owner',
    color: 'purple',
    classes: 'bg-purple-100 dark:bg-purple-900/30 text-purple-900 dark:text-purple-200 border-purple-300 dark:border-purple-700',
  },
  admin: {
    label: 'Admin',
    color: 'blue',
    classes: 'bg-blue-100 dark:bg-blue-900/30 text-blue-900 dark:text-blue-200 border-blue-300 dark:border-blue-700',
  },
  member: {
    label: 'Member',
    color: 'green',
    classes: 'bg-green-100 dark:bg-green-900/30 text-green-900 dark:text-green-200 border-green-300 dark:border-green-700',
  },
  readonly: {
    label: 'Read-Only',
    color: 'gray',
    classes: 'bg-gray-100 dark:bg-gray-700/30 text-gray-900 dark:text-gray-200 border-gray-300 dark:border-gray-600',
  },
  global_admin: {
    label: 'Global Admin',
    color: 'purple',
    classes: 'bg-purple-100 dark:bg-purple-900/30 text-purple-900 dark:text-purple-200 border-purple-300 dark:border-purple-700',
  },
}

export default function RoleBadge({ role, size = 'md' }: RoleBadgeProps) {
  const config = roleConfig[role as keyof typeof roleConfig] || roleConfig.member
  const Icon = ROLE_ICON_MAP[role] || ROLE_ICON_MAP.member

  const sizeClasses = {
    sm: 'text-xs px-2 py-0.5',
    md: 'text-sm px-2.5 py-1',
    lg: 'text-base px-3 py-1.5',
  }

  return (
    <span
      className={`inline-flex items-center space-x-1 font-medium rounded-full border ${config.classes} ${sizeClasses[size]}`}
    >
      <Icon size={14} />
      <span>{config.label}</span>
    </span>
  )
}
