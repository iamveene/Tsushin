'use client'

/**
 * User Profile Page
 * Shows detailed user information, activity, permissions, and security settings
 */

import { useState } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import RoleBadge from '@/components/rbac/RoleBadge'
import RoleSelector from '@/components/rbac/RoleSelector'

// Mock user data
const MOCK_USER = {
  id: 3,
  name: 'João Silva',
  email: 'joao@example.com',
  role: 'member',
  status: 'active',
  joinedAt: 'Jan 15, 2025',
  lastActive: '3 days ago',
  lastLogin: 'Jan 28, 2025 14:32',
  ipAddress: '192.168.1.102',
  twoFactorEnabled: false,
}

const MOCK_ACTIVITY = [
  { id: 1, action: 'Created agent "Marketing Bot"', timestamp: '1 day ago' },
  { id: 2, action: 'Updated contact "Customer A"', timestamp: '2 days ago' },
  { id: 3, action: 'Executed agent "Support Bot"', timestamp: '3 days ago' },
  { id: 4, action: 'Logged in', timestamp: '3 days ago' },
  { id: 5, action: 'Connected Telegram integration', timestamp: '1 week ago' },
]

const MOCK_PERMISSIONS = [
  { category: 'Agents', permissions: ['Read', 'Write', 'Execute'] },
  { category: 'Contacts', permissions: ['Read', 'Write'] },
  { category: 'Memory', permissions: ['Read', 'Write'] },
  { category: 'Integrations', permissions: ['Read', 'Link', 'Configure'] },
]

export default function UserProfilePage() {
  const router = useRouter()
  const params = useParams()
  const { user: currentUser, hasPermission } = useAuth()
  const [activeTab, setActiveTab] = useState<'activity' | 'permissions' | 'security'>('activity')
  const [user, setUser] = useState(MOCK_USER)
  const [isEditingRole, setIsEditingRole] = useState(false)

  const canManage = hasPermission('users.manage')
  const isOwnProfile = currentUser?.id === user.id

  if (!hasPermission('users.read')) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-red-900 dark:text-red-100 mb-2">
            Access Denied
          </h3>
          <p className="text-sm text-red-800 dark:text-red-200">
            You don't have permission to view user profiles.
          </p>
        </div>
      </div>
    )
  }

  const handleRoleChange = (newRole: string) => {
    setUser({ ...user, role: newRole })
    setIsEditingRole(false)
    alert(`Role changed to ${newRole} (mock)`)
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-6xl mx-auto">
        {/* Back Button */}
        <button
          onClick={() => router.back()}
          className="text-sm text-blue-600 dark:text-blue-400 hover:underline mb-6"
        >
          ← Back to Team
        </button>

        {/* User Header */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 mb-6">
          <div className="flex items-start justify-between">
            <div className="flex items-start space-x-6">
              {/* Avatar */}
              <div className="w-20 h-20 rounded-full bg-gradient-to-br from-blue-500 to-purple-500 flex items-center justify-center text-white font-bold text-2xl">
                {user.name
                  .split(' ')
                  .map((n) => n[0])
                  .join('')
                  .toUpperCase()}
              </div>

              {/* Info */}
              <div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-1">
                  {user.name}
                  {isOwnProfile && (
                    <span className="ml-3 text-sm font-normal text-gray-600 dark:text-gray-400">
                      (You)
                    </span>
                  )}
                </h1>
                <p className="text-gray-600 dark:text-gray-400 mb-3">{user.email}</p>

                <div className="flex items-center space-x-4 mb-3">
                  {!isEditingRole ? (
                    <>
                      <RoleBadge role={user.role} />
                      {canManage && user.role !== 'owner' && (
                        <button
                          onClick={() => setIsEditingRole(true)}
                          className="text-sm text-blue-600 dark:text-blue-400 hover:underline"
                        >
                          Change Role
                        </button>
                      )}
                    </>
                  ) : (
                    <div className="flex items-center space-x-2">
                      <RoleSelector
                        currentRole={user.role}
                        onChange={handleRoleChange}
                        disabled={false}
                      />
                      <button
                        onClick={() => setIsEditingRole(false)}
                        className="text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100"
                      >
                        Cancel
                      </button>
                    </div>
                  )}
                </div>

                <div className="flex items-center space-x-4 text-sm text-gray-600 dark:text-gray-400">
                  <span>Joined {user.joinedAt}</span>
                  <span>•</span>
                  <span>Last active {user.lastActive}</span>
                </div>
              </div>
            </div>

            {/* Actions */}
            {canManage && user.role !== 'owner' && (
              <div className="flex items-center space-x-2">
                <button className="px-4 py-2 bg-yellow-100 dark:bg-yellow-900/30 text-yellow-900 dark:text-yellow-200 text-sm font-medium rounded-md hover:bg-yellow-200 dark:hover:bg-yellow-900/50 transition-colors">
                  {user.status === 'active' ? 'Suspend' : 'Reactivate'}
                </button>
                <button className="px-4 py-2 bg-red-100 dark:bg-red-900/30 text-red-900 dark:text-red-200 text-sm font-medium rounded-md hover:bg-red-200 dark:hover:bg-red-900/50 transition-colors">
                  Remove
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Tabs */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
          <div className="border-b border-gray-200 dark:border-gray-700">
            <nav className="flex space-x-8 px-6" aria-label="Tabs">
              {(['activity', 'permissions', 'security'] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`py-4 px-1 border-b-2 font-medium text-sm capitalize transition-colors ${
                    activeTab === tab
                      ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                      : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600'
                  }`}
                >
                  {tab}
                </button>
              ))}
            </nav>
          </div>

          {/* Tab Content */}
          <div className="p-6">
            {/* Activity Tab */}
            {activeTab === 'activity' && (
              <div className="space-y-4">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
                  Recent Activity
                </h3>
                {MOCK_ACTIVITY.map((activity) => (
                  <div
                    key={activity.id}
                    className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-900/50 rounded-lg"
                  >
                    <span className="text-sm text-gray-700 dark:text-gray-300">
                      {activity.action}
                    </span>
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      {activity.timestamp}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* Permissions Tab */}
            {activeTab === 'permissions' && (
              <div className="space-y-6">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  Current Permissions
                </h3>
                {MOCK_PERMISSIONS.map((category) => (
                  <div key={category.category}>
                    <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">
                      {category.category}
                    </h4>
                    <div className="flex flex-wrap gap-2">
                      {category.permissions.map((perm) => (
                        <span
                          key={perm}
                          className="px-3 py-1 bg-green-100 dark:bg-green-900/30 text-green-900 dark:text-green-200 text-sm rounded-full"
                        >
                          ✓ {perm}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Security Tab */}
            {activeTab === 'security' && (
              <div className="space-y-6">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
                  Security Settings
                </h3>

                <div className="space-y-4">
                  <div className="flex items-center justify-between p-4 border border-gray-200 dark:border-gray-700 rounded-lg">
                    <div>
                      <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100">
                        Two-Factor Authentication
                      </h4>
                      <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                        {user.twoFactorEnabled ? 'Enabled' : 'Not enabled'}
                      </p>
                    </div>
                    <button className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-md transition-colors">
                      {user.twoFactorEnabled ? 'Disable' : 'Enable'}
                    </button>
                  </div>

                  <div className="p-4 border border-gray-200 dark:border-gray-700 rounded-lg">
                    <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                      Last Login
                    </h4>
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      {user.lastLogin} from {user.ipAddress}
                    </p>
                  </div>

                  {isOwnProfile && (
                    <div className="p-4 border border-gray-200 dark:border-gray-700 rounded-lg">
                      <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-3">
                        Password
                      </h4>
                      <button className="px-4 py-2 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 text-gray-900 dark:text-gray-100 text-sm font-medium rounded-md transition-colors">
                        Change Password
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
