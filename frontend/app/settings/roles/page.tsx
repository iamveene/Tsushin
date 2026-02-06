'use client'

/**
 * Roles & Permissions Page
 * Shows role overview and detailed permissions
 */

import { useState } from 'react'
import Link from 'next/link'
import { useAuth } from '@/contexts/AuthContext'
import RoleBadge from '@/components/rbac/RoleBadge'
import PermissionMatrix from '@/components/rbac/PermissionMatrix'
import { CrownIcon, ShieldIcon, UserIcon, EyeIcon, CheckIcon, XIcon } from '@/components/ui/icons'

const ROLES = [
  {
    name: 'owner',
    displayName: 'Owner',
    Icon: CrownIcon,
    description: 'Complete control over the organization including billing and team management.',
    permissions: [
      'All agent permissions',
      'All contact & memory permissions',
      'All integration permissions',
      'Invite and manage team members',
      'Change user roles',
      'View and manage billing',
      'Organization settings',
      'Delete organization',
    ],
    limitations: [],
    color: 'purple',
  },
  {
    name: 'admin',
    displayName: 'Admin',
    Icon: ShieldIcon,
    description: 'Full administrative access except billing. Can manage all resources and team members.',
    permissions: [
      'All agent permissions',
      'All contact & memory permissions',
      'All integration permissions',
      'Invite and manage team members',
      'Change user roles',
      'Organization settings',
      'View audit logs',
    ],
    limitations: ['Cannot access billing', 'Cannot delete organization'],
    color: 'blue',
  },
  {
    name: 'member',
    displayName: 'Member',
    Icon: UserIcon,
    description: 'Standard user role. Can create and manage their own resources.',
    permissions: [
      'Create and manage own agents',
      'Manage own contacts',
      'Manage own memory',
      'Connect own integrations',
      'Execute agents',
    ],
    limitations: [
      'Cannot manage team members',
      'Cannot access billing',
      'Cannot change organization settings',
      'Cannot delete other users\' resources',
    ],
    color: 'green',
  },
  {
    name: 'readonly',
    displayName: 'Read-Only',
    Icon: EyeIcon,
    description: 'View-only access. Perfect for observers who need to monitor but not make changes.',
    permissions: ['View agents', 'View contacts', 'View memory', 'View integrations'],
    limitations: [
      'Cannot create or modify anything',
      'Cannot execute agents',
      'Cannot access team management',
      'Cannot access billing',
    ],
    color: 'gray',
  },
]

export default function RolesPage() {
  const { hasPermission } = useAuth()
  const [showMatrix, setShowMatrix] = useState(false)

  if (!hasPermission('users.read')) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-red-900 dark:text-red-100 mb-2">
            Access Denied
          </h3>
          <p className="text-sm text-red-800 dark:text-red-200">
            You don't have permission to view roles and permissions.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">
              Roles & Permissions
            </h1>
            <p className="text-gray-600 dark:text-gray-400 mt-2">
              Understand what each role can do in your organization
            </p>
          </div>

          <button
            onClick={() => setShowMatrix(true)}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-md transition-colors"
          >
            View Permission Matrix
          </button>
        </div>

        {/* Back to Settings */}
        <Link
          href="/settings"
          className="inline-flex items-center gap-2 text-sm text-teal-400 hover:text-teal-300 mb-6 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Back to Settings
        </Link>

        {/* Role Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {ROLES.map((role) => (
            <div
              key={role.name}
              className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 hover:shadow-lg transition-shadow"
            >
              {/* Role Header */}
              <div className="flex items-center space-x-4 mb-4">
                <role.Icon size={36} />
                <div className="flex-1">
                  <h3 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
                    {role.displayName}
                  </h3>
                  <RoleBadge role={role.name} size="sm" />
                </div>
              </div>

              {/* Description */}
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                {role.description}
              </p>

              {/* Permissions */}
              <div className="mb-4">
                <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2 flex items-center gap-1">
                  <CheckIcon size={14} className="text-green-600 dark:text-green-400" /> Permissions:
                </h4>
                <ul className="space-y-1">
                  {role.permissions.map((perm, idx) => (
                    <li key={idx} className="text-sm text-gray-700 dark:text-gray-300 flex items-start">
                      <span className="text-green-600 dark:text-green-400 mr-2">•</span>
                      {perm}
                    </li>
                  ))}
                </ul>
              </div>

              {/* Limitations */}
              {role.limitations.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2 flex items-center gap-1">
                    <XIcon size={14} className="text-red-600 dark:text-red-400" /> Limitations:
                  </h4>
                  <ul className="space-y-1">
                    {role.limitations.map((limit, idx) => (
                      <li key={idx} className="text-sm text-gray-700 dark:text-gray-300 flex items-start">
                        <span className="text-red-600 dark:text-red-400 mr-2">•</span>
                        {limit}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Role Hierarchy Info */}
        <div className="mt-8 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-blue-900 dark:text-blue-100 mb-3">
            Role Hierarchy
          </h3>
          <div className="text-sm text-blue-800 dark:text-blue-200">
            <p className="mb-2">
              Roles are hierarchical, meaning higher roles inherit all permissions from lower roles:
            </p>
            <div className="font-mono bg-white dark:bg-gray-800 rounded p-4 text-gray-900 dark:text-gray-100">
              <div className="flex items-center gap-1"><CrownIcon size={14} /> Owner</div>
              <div className="ml-4 flex items-center gap-1">└─ <ShieldIcon size={14} /> Admin</div>
              <div className="ml-8 flex items-center gap-1">└─ <UserIcon size={14} /> Member</div>
              <div className="ml-12 flex items-center gap-1">└─ <EyeIcon size={14} /> Read-Only</div>
            </div>
          </div>
        </div>
      </div>

      {/* Permission Matrix Modal */}
      {showMatrix && <PermissionMatrix onClose={() => setShowMatrix(false)} />}
    </div>
  )
}
