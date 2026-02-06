'use client'

/**
 * Permission Matrix Component
 * Shows detailed permission breakdown for all roles
 */

import { CrownIcon, ShieldIcon, UserIcon, EyeIcon, CheckIcon, XIcon } from '@/components/ui/icons'

interface Permission {
  category: string
  action: string
  owner: boolean
  admin: boolean
  member: boolean
  readonly: boolean
}

const PERMISSIONS: Permission[] = [
  // Agents
  { category: 'Agents', action: 'Read', owner: true, admin: true, member: true, readonly: true },
  { category: 'Agents', action: 'Write', owner: true, admin: true, member: true, readonly: false },
  { category: 'Agents', action: 'Delete', owner: true, admin: true, member: false, readonly: false },
  { category: 'Agents', action: 'Execute', owner: true, admin: true, member: true, readonly: false },

  // Contacts
  { category: 'Contacts', action: 'Read', owner: true, admin: true, member: true, readonly: true },
  { category: 'Contacts', action: 'Write', owner: true, admin: true, member: true, readonly: false },
  { category: 'Contacts', action: 'Delete', owner: true, admin: true, member: false, readonly: false },

  // Memory
  { category: 'Memory', action: 'Read', owner: true, admin: true, member: true, readonly: true },
  { category: 'Memory', action: 'Write', owner: true, admin: true, member: true, readonly: false },
  { category: 'Memory', action: 'Clear', owner: true, admin: true, member: false, readonly: false },

  // Integrations
  { category: 'Integrations', action: 'Read', owner: true, admin: true, member: true, readonly: true },
  { category: 'Integrations', action: 'Link', owner: true, admin: true, member: true, readonly: false },
  { category: 'Integrations', action: 'Configure', owner: true, admin: true, member: true, readonly: false },
  { category: 'Integrations', action: 'Unlink', owner: true, admin: true, member: true, readonly: false },

  // Users
  { category: 'Users', action: 'Read', owner: true, admin: true, member: false, readonly: false },
  { category: 'Users', action: 'Invite', owner: true, admin: true, member: false, readonly: false },
  { category: 'Users', action: 'Remove', owner: true, admin: true, member: false, readonly: false },
  { category: 'Users', action: 'Change Roles', owner: true, admin: true, member: false, readonly: false },

  // Organization Settings
  { category: 'Organization', action: 'Read', owner: true, admin: true, member: false, readonly: false },
  { category: 'Organization', action: 'Write', owner: true, admin: true, member: false, readonly: false },
  { category: 'Organization', action: 'Delete', owner: true, admin: false, member: false, readonly: false },

  // Billing
  { category: 'Billing', action: 'Read', owner: true, admin: false, member: false, readonly: false },
  { category: 'Billing', action: 'Manage', owner: true, admin: false, member: false, readonly: false },
]

interface PermissionMatrixProps {
  onClose?: () => void
}

export default function PermissionMatrix({ onClose }: PermissionMatrixProps) {
  const categories = [...new Set(PERMISSIONS.map(p => p.category))]

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-5xl w-full max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            Permission Matrix
          </h2>
          {onClose && (
            <button
              onClick={onClose}
              className="p-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700"
            >
              <XIcon size={18} />
            </button>
          )}
        </div>

        {/* Content */}
        <div className="p-6 overflow-auto max-h-[calc(90vh-120px)]">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr className="bg-gray-50 dark:bg-gray-900">
                  <th className="px-4 py-3 text-left text-sm font-semibold text-gray-900 dark:text-gray-100 border-b border-gray-200 dark:border-gray-700">
                    Category
                  </th>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-gray-900 dark:text-gray-100 border-b border-gray-200 dark:border-gray-700">
                    Action
                  </th>
                  <th className="px-4 py-3 text-center text-sm font-semibold text-purple-900 dark:text-purple-200 border-b border-gray-200 dark:border-gray-700">
                    <span className="inline-flex items-center justify-center gap-1"><CrownIcon size={16} /> Owner</span>
                  </th>
                  <th className="px-4 py-3 text-center text-sm font-semibold text-blue-900 dark:text-blue-200 border-b border-gray-200 dark:border-gray-700">
                    <span className="inline-flex items-center justify-center gap-1"><ShieldIcon size={16} /> Admin</span>
                  </th>
                  <th className="px-4 py-3 text-center text-sm font-semibold text-green-900 dark:text-green-200 border-b border-gray-200 dark:border-gray-700">
                    <span className="inline-flex items-center justify-center gap-1"><UserIcon size={16} /> Member</span>
                  </th>
                  <th className="px-4 py-3 text-center text-sm font-semibold text-gray-900 dark:text-gray-200 border-b border-gray-200 dark:border-gray-700">
                    <span className="inline-flex items-center justify-center gap-1"><EyeIcon size={16} /> Read-Only</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {categories.map((category) => {
                  const categoryPerms = PERMISSIONS.filter(p => p.category === category)
                  return categoryPerms.map((perm, idx) => (
                    <tr key={`${category}-${perm.action}`} className="hover:bg-gray-50 dark:hover:bg-gray-900/50">
                      {idx === 0 && (
                        <td
                          rowSpan={categoryPerms.length}
                          className="px-4 py-3 text-sm font-medium text-gray-900 dark:text-gray-100 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/30"
                        >
                          {category}
                        </td>
                      )}
                      <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300 border-b border-gray-200 dark:border-gray-700">
                        {perm.action}
                      </td>
                      <td className="px-4 py-3 text-center border-b border-gray-200 dark:border-gray-700">
                        <span className="inline-flex justify-center">
                          {perm.owner ? (
                            <CheckIcon size={18} className="text-green-600 dark:text-green-400" />
                          ) : (
                            <XIcon size={18} className="text-red-600 dark:text-red-400" />
                          )}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center border-b border-gray-200 dark:border-gray-700">
                        <span className="inline-flex justify-center">
                          {perm.admin ? (
                            <CheckIcon size={18} className="text-green-600 dark:text-green-400" />
                          ) : (
                            <XIcon size={18} className="text-red-600 dark:text-red-400" />
                          )}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center border-b border-gray-200 dark:border-gray-700">
                        <span className="inline-flex justify-center">
                          {perm.member ? (
                            <CheckIcon size={18} className="text-green-600 dark:text-green-400" />
                          ) : (
                            <XIcon size={18} className="text-red-600 dark:text-red-400" />
                          )}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center border-b border-gray-200 dark:border-gray-700">
                        <span className="inline-flex justify-center">
                          {perm.readonly ? (
                            <CheckIcon size={18} className="text-green-600 dark:text-green-400" />
                          ) : (
                            <XIcon size={18} className="text-red-600 dark:text-red-400" />
                          )}
                        </span>
                      </td>
                    </tr>
                  ))
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end p-6 border-t border-gray-200 dark:border-gray-700">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 text-gray-900 dark:text-gray-100 font-medium rounded-md transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
