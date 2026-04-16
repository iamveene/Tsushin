'use client'

/**
 * User Profile Page
 * Shows detailed user information, activity, permissions, and security settings
 */

import { useState, useEffect } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import { api, TeamMember } from '@/lib/client'
import RoleBadge from '@/components/rbac/RoleBadge'
import RoleSelector from '@/components/rbac/RoleSelector'

export default function UserProfilePage() {
  const router = useRouter()
  const params = useParams()
  const userId = Number(params.id)
  const { user: currentUser, hasPermission } = useAuth()
  const [activeTab, setActiveTab] = useState<'activity' | 'permissions' | 'security'>('activity')
  const [user, setUser] = useState<TeamMember | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isEditingRole, setIsEditingRole] = useState(false)

  const canManage = hasPermission('users.manage')
  const isOwnProfile = currentUser?.id === userId

  useEffect(() => {
    if (!userId || !hasPermission('users.read')) return
    setLoading(true)
    api
      .getTeamMember(userId)
      .then((data) => {
        setUser(data)
        setError(null)
      })
      .catch((err) => {
        console.error('Failed to fetch team member:', err)
        setError('Failed to load user profile')
      })
      .finally(() => setLoading(false))
  }, [userId, hasPermission])

  if (!hasPermission('users.read')) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-red-900 dark:text-red-100 mb-2">
            Access Denied
          </h3>
          <p className="text-sm text-red-800 dark:text-red-200">
            You don&apos;t have permission to view user profiles.
          </p>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="max-w-6xl mx-auto text-center py-12">
          <p className="text-gray-600 dark:text-gray-400">Loading user profile...</p>
        </div>
      </div>
    )
  }

  if (error || !user) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="max-w-6xl mx-auto">
          <button
            onClick={() => router.back()}
            className="text-sm text-blue-600 dark:text-blue-400 hover:underline mb-6"
          >
            &larr; Back to Team
          </button>
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6">
            <p className="text-sm text-red-800 dark:text-red-200">
              {error || 'User not found'}
            </p>
          </div>
        </div>
      </div>
    )
  }

  const handleRoleChange = async (newRole: string) => {
    try {
      const updated = await api.changeTeamMemberRole(userId, newRole)
      setUser(updated)
      setIsEditingRole(false)
    } catch (err) {
      console.error('Failed to change role:', err)
      alert(err instanceof Error ? err.message : 'Failed to change role')
    }
  }

  const displayName = user.full_name || user.email

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-6xl mx-auto">
        {/* Back Button */}
        <button
          onClick={() => router.back()}
          className="text-sm text-blue-600 dark:text-blue-400 hover:underline mb-6"
        >
          &larr; Back to Team
        </button>

        {/* User Header */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 mb-6">
          <div className="flex items-start justify-between">
            <div className="flex items-start space-x-6">
              {/* Avatar */}
              <div className="w-20 h-20 rounded-full bg-gradient-to-br from-blue-500 to-purple-500 flex items-center justify-center text-white font-bold text-2xl">
                {user.avatar_url ? (
                  <img src={user.avatar_url} alt={displayName} className="w-20 h-20 rounded-full object-cover" />
                ) : (
                  displayName
                    .split(' ')
                    .map((n) => n[0])
                    .join('')
                    .toUpperCase()
                    .slice(0, 2)
                )}
              </div>

              {/* Info */}
              <div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-1">
                  {displayName}
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
                  {user.created_at && <span>Joined {new Date(user.created_at).toLocaleDateString()}</span>}
                  {user.last_login_at && (
                    <>
                      <span>-</span>
                      <span>Last login {new Date(user.last_login_at).toLocaleDateString()}</span>
                    </>
                  )}
                </div>
              </div>
            </div>

            {/* Actions */}
            {canManage && user.role !== 'owner' && (
              <div className="flex items-center space-x-2">
                <button className="px-4 py-2 bg-yellow-100 dark:bg-yellow-900/30 text-yellow-900 dark:text-yellow-200 text-sm font-medium rounded-md hover:bg-yellow-200 dark:hover:bg-yellow-900/50 transition-colors">
                  {user.is_active ? 'Suspend' : 'Reactivate'}
                </button>
                <button
                  onClick={async () => {
                    if (confirm('Are you sure you want to remove this team member?')) {
                      try {
                        await api.removeTeamMember(userId)
                        router.push('/settings/team')
                      } catch (err) {
                        alert(err instanceof Error ? err.message : 'Failed to remove member')
                      }
                    }
                  }}
                  className="px-4 py-2 bg-red-100 dark:bg-red-900/30 text-red-900 dark:text-red-200 text-sm font-medium rounded-md hover:bg-red-200 dark:hover:bg-red-900/50 transition-colors"
                >
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
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Activity tracking for individual users is not yet available.
                </p>
              </div>
            )}

            {/* Permissions Tab */}
            {activeTab === 'permissions' && (
              <div className="space-y-6">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  Current Role
                </h3>
                <div className="p-4 bg-gray-50 dark:bg-gray-900/50 rounded-lg">
                  <RoleBadge role={user.role} />
                  <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">
                    Role: <strong>{user.role_display_name}</strong>
                  </p>
                </div>
              </div>
            )}

            {/* Security Tab */}
            {activeTab === 'security' && (
              <div className="space-y-6">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
                  Security Settings
                </h3>

                <div className="space-y-4">
                  <div className="p-4 border border-gray-200 dark:border-gray-700 rounded-lg">
                    <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                      Account Status
                    </h4>
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      {user.is_active ? 'Active' : 'Inactive'} &middot; {user.email_verified ? 'Email verified' : 'Email not verified'}
                    </p>
                  </div>

                  <div className="p-4 border border-gray-200 dark:border-gray-700 rounded-lg">
                    <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                      Authentication Provider
                    </h4>
                    <p className="text-sm text-gray-600 dark:text-gray-400 capitalize">
                      {user.auth_provider}
                    </p>
                  </div>

                  {user.last_login_at && (
                    <div className="p-4 border border-gray-200 dark:border-gray-700 rounded-lg">
                      <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                        Last Login
                      </h4>
                      <p className="text-sm text-gray-600 dark:text-gray-400">
                        {new Date(user.last_login_at).toLocaleString()}
                      </p>
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
