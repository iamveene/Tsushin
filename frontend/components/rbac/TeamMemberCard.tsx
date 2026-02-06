'use client'

/**
 * Team Member Card Component
 * Displays individual team member with actions
 */

import { useState } from 'react'
import Link from 'next/link'
import RoleBadge from './RoleBadge'
import RoleSelector from './RoleSelector'

// Google Icon for SSO badge
const GoogleIcon = () => (
  <svg className="w-3.5 h-3.5" viewBox="0 0 24 24">
    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
  </svg>
)

interface TeamMember {
  id: number
  name: string
  email: string
  role: string
  status: 'active' | 'suspended'
  lastActive: string
  authProvider?: string
  avatarUrl?: string | null
}

interface TeamMemberCardProps {
  member: TeamMember
  canEdit: boolean
  onRoleChange?: (memberId: number, newRole: string) => void
  onSuspend?: (memberId: number) => void
  onRemove?: (memberId: number) => void
}

export default function TeamMemberCard({
  member,
  canEdit,
  onRoleChange,
  onSuspend,
  onRemove,
}: TeamMemberCardProps) {
  const [isEditingRole, setIsEditingRole] = useState(false)
  const [showActions, setShowActions] = useState(false)

  const handleRoleChange = (newRole: string) => {
    if (onRoleChange) {
      onRoleChange(member.id, newRole)
    }
    setIsEditingRole(false)
  }

  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between">
        <div className="flex items-start space-x-4">
          {/* Avatar */}
          {member.avatarUrl ? (
            <img
              src={member.avatarUrl}
              alt={member.name}
              className="w-12 h-12 rounded-full object-cover"
            />
          ) : (
            <div className="w-12 h-12 rounded-full bg-gradient-to-br from-blue-500 to-purple-500 flex items-center justify-center text-white font-semibold text-lg">
              {member.name
                .split(' ')
                .map((n) => n[0])
                .join('')
                .toUpperCase()
                .slice(0, 2)}
            </div>
          )}

          {/* Info */}
          <div className="flex-1">
            <div className="flex items-center space-x-3">
              <Link
                href={`/settings/team/${member.id}`}
                className="text-lg font-semibold text-gray-900 dark:text-gray-100 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
              >
                {member.name}
              </Link>
              {/* Auth Method Badge */}
              {member.authProvider === 'google' && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-700 rounded-full">
                  <GoogleIcon />
                  SSO
                </span>
              )}
              {member.status === 'suspended' && (
                <span className="px-2 py-0.5 text-xs font-medium bg-red-100 dark:bg-red-900/30 text-red-900 dark:text-red-200 border border-red-300 dark:border-red-700 rounded-full">
                  Suspended
                </span>
              )}
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">{member.email}</p>
            <div className="flex items-center space-x-4 mt-2">
              <RoleBadge role={member.role} size="sm" />
              <span className="text-xs text-gray-500 dark:text-gray-400">
                Last active: {member.lastActive}
              </span>
            </div>
          </div>
        </div>

        {/* Actions */}
        {canEdit && member.role !== 'owner' && (
          <div className="relative">
            <button
              onClick={() => setShowActions(!showActions)}
              className="p-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md transition-colors"
            >
              <svg
                className="w-5 h-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z"
                />
              </svg>
            </button>

            {showActions && (
              <div className="absolute right-0 mt-2 w-48 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-10">
                <div className="py-1">
                  <button
                    onClick={() => {
                      setIsEditingRole(true)
                      setShowActions(false)
                    }}
                    className="w-full text-left px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
                  >
                    Change Role
                  </button>
                  <button
                    onClick={() => {
                      if (onSuspend) onSuspend(member.id)
                      setShowActions(false)
                    }}
                    className="w-full text-left px-4 py-2 text-sm text-yellow-700 dark:text-yellow-300 hover:bg-gray-100 dark:hover:bg-gray-700"
                  >
                    {member.status === 'active' ? 'Suspend' : 'Reactivate'}
                  </button>
                  <button
                    onClick={() => {
                      if (confirm(`Remove ${member.name} from the organization?`)) {
                        if (onRemove) onRemove(member.id)
                      }
                      setShowActions(false)
                    }}
                    className="w-full text-left px-4 py-2 text-sm text-red-700 dark:text-red-300 hover:bg-gray-100 dark:hover:bg-gray-700"
                  >
                    Remove
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Role Editor */}
      {isEditingRole && (
        <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
          <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
            Change Role
          </label>
          <div className="flex items-center space-x-2">
            <RoleSelector
              currentRole={member.role}
              onChange={handleRoleChange}
              disabled={false}
            />
            <button
              onClick={() => setIsEditingRole(false)}
              className="px-3 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
