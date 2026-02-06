'use client'

/**
 * Global Users Management Page (Global Admin Only)
 * Manage users across all tenants
 */

import { useState, useEffect, useCallback } from 'react'
import { useRequireGlobalAdmin } from '@/contexts/AuthContext'
import { api, GlobalUser, GlobalUserStats, TenantInfo, UserCreateRequest, UserUpdateRequest } from '@/lib/client'

export default function GlobalUsersPage() {
  const { user, loading: authLoading } = useRequireGlobalAdmin()
  const [users, setUsers] = useState<GlobalUser[]>([])
  const [stats, setStats] = useState<GlobalUserStats | null>(null)
  const [tenants, setTenants] = useState<TenantInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Filters
  const [search, setSearch] = useState('')
  const [tenantFilter, setTenantFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState<'active' | 'inactive' | 'all'>('all')
  const [authFilter, setAuthFilter] = useState<'' | 'local' | 'google'>('')
  const [adminFilter, setAdminFilter] = useState<'' | 'true' | 'false'>('')

  // Pagination
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const pageSize = 25

  // Modal state
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [editingUser, setEditingUser] = useState<GlobalUser | null>(null)
  const [modalLoading, setModalLoading] = useState(false)
  const [modalError, setModalError] = useState<string | null>(null)

  // Create form state
  const [createForm, setCreateForm] = useState({
    email: '',
    password: '',
    full_name: '',
    tenant_id: '',
    role_name: 'member',
  })

  // Fetch users
  const fetchUsers = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await api.getGlobalUsers({
        search: search || undefined,
        tenant_id: tenantFilter || undefined,
        status: statusFilter,
        auth_provider: authFilter || undefined,
        is_global_admin: adminFilter === '' ? undefined : adminFilter === 'true',
        page,
        page_size: pageSize,
      })
      setUsers(response.users)
      setTotal(response.total)
    } catch (err: any) {
      console.error('Failed to fetch users:', err)
      setError(err.message || 'Failed to load users')
    } finally {
      setLoading(false)
    }
  }, [search, tenantFilter, statusFilter, authFilter, adminFilter, page])

  // Fetch stats and tenants
  const fetchStatsAndTenants = useCallback(async () => {
    try {
      const [statsRes, tenantsRes] = await Promise.all([
        api.getGlobalUserStats(),
        api.getTenants({ page_size: 100 }),
      ])
      setStats(statsRes)
      setTenants(tenantsRes.tenants)
    } catch (err) {
      console.error('Failed to fetch stats/tenants:', err)
    }
  }, [])

  useEffect(() => {
    if (!authLoading && user) {
      fetchUsers()
      fetchStatsAndTenants()
    }
  }, [fetchUsers, fetchStatsAndTenants, authLoading, user])

  // Reset page when filters change
  useEffect(() => {
    setPage(1)
  }, [search, tenantFilter, statusFilter, authFilter, adminFilter])

  // Listen for global refresh events
  useEffect(() => {
    const handleRefresh = () => {
      fetchUsers()
      fetchStatsAndTenants()
    }
    window.addEventListener('tsushin:refresh', handleRefresh)
    return () => window.removeEventListener('tsushin:refresh', handleRefresh)
  }, [fetchUsers, fetchStatsAndTenants])

  // Handle create user
  const handleCreate = async () => {
    setModalLoading(true)
    setModalError(null)
    try {
      await api.createGlobalUser({
        email: createForm.email,
        password: createForm.password,
        full_name: createForm.full_name,
        tenant_id: createForm.tenant_id,
        role_name: createForm.role_name,
      })
      setShowCreateModal(false)
      setCreateForm({ email: '', password: '', full_name: '', tenant_id: '', role_name: 'member' })
      fetchUsers()
      fetchStatsAndTenants()
    } catch (err: any) {
      setModalError(err.message || 'Failed to create user')
    } finally {
      setModalLoading(false)
    }
  }

  // Handle update user
  const handleUpdate = async (updates: UserUpdateRequest) => {
    if (!editingUser) return
    setModalLoading(true)
    setModalError(null)
    try {
      await api.updateGlobalUser(editingUser.id, updates)
      setEditingUser(null)
      fetchUsers()
      fetchStatsAndTenants()
    } catch (err: any) {
      setModalError(err.message || 'Failed to update user')
    } finally {
      setModalLoading(false)
    }
  }

  // Handle toggle status
  const handleToggleStatus = async (u: GlobalUser) => {
    try {
      await api.updateGlobalUser(u.id, { is_active: !u.is_active })
      fetchUsers()
      fetchStatsAndTenants()
    } catch (err: any) {
      alert(err.message || 'Failed to update user status')
    }
  }

  // Handle toggle admin
  const handleToggleAdmin = async (u: GlobalUser) => {
    if (!confirm(`Are you sure you want to ${u.is_global_admin ? 'revoke' : 'grant'} global admin status?`)) return
    try {
      await api.toggleGlobalAdmin(u.id)
      fetchUsers()
      fetchStatsAndTenants()
    } catch (err: any) {
      alert(err.message || 'Failed to toggle admin status')
    }
  }

  // Handle delete
  const handleDelete = async (u: GlobalUser) => {
    if (!confirm(`Are you sure you want to delete user ${u.email}?`)) return
    try {
      await api.deleteGlobalUser(u.id)
      fetchUsers()
      fetchStatsAndTenants()
    } catch (err: any) {
      alert(err.message || 'Failed to delete user')
    }
  }

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-gray-600 dark:text-gray-400">Loading...</div>
      </div>
    )
  }

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <div className="flex items-center space-x-3 mb-2">
              <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">
                User Management
              </h1>
              <span className="px-3 py-1 bg-purple-100 dark:bg-purple-900/30 text-purple-900 dark:text-purple-200 text-sm font-semibold rounded-full">
                Global Admin
              </span>
            </div>
            <p className="text-gray-600 dark:text-gray-400">
              Manage users across all organizations
            </p>
          </div>

          <button
            onClick={() => setShowCreateModal(true)}
            className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white font-medium rounded-md transition-colors"
          >
            + Create User
          </button>
        </div>

        {/* Stats */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
              <div className="text-sm text-gray-600 dark:text-gray-400">Total Users</div>
              <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">{stats.total_users}</div>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
              <div className="text-sm text-gray-600 dark:text-gray-400">Active</div>
              <div className="text-2xl font-bold text-green-600">{stats.active_users}</div>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
              <div className="text-sm text-gray-600 dark:text-gray-400">Global Admins</div>
              <div className="text-2xl font-bold text-purple-600">{stats.global_admins}</div>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
              <div className="text-sm text-gray-600 dark:text-gray-400">Google SSO</div>
              <div className="text-2xl font-bold text-blue-600">{stats.google_sso_users}</div>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
              <div className="text-sm text-gray-600 dark:text-gray-400">Local Auth</div>
              <div className="text-2xl font-bold text-gray-600">{stats.local_users}</div>
            </div>
          </div>
        )}

        {/* Filters */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 mb-6">
          <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
            <input
              type="text"
              placeholder="Search by email or name..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700"
            />
            <select
              value={tenantFilter}
              onChange={(e) => setTenantFilter(e.target.value)}
              className="px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700"
            >
              <option value="">All Organizations</option>
              {tenants.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as any)}
              className="px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700"
            >
              <option value="all">All Status</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
            <select
              value={authFilter}
              onChange={(e) => setAuthFilter(e.target.value as any)}
              className="px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700"
            >
              <option value="">All Auth Methods</option>
              <option value="local">Local</option>
              <option value="google">Google SSO</option>
            </select>
            <select
              value={adminFilter}
              onChange={(e) => setAdminFilter(e.target.value as any)}
              className="px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700"
            >
              <option value="">All Users</option>
              <option value="true">Global Admins</option>
              <option value="false">Regular Users</option>
            </select>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-6 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
            <p className="text-sm text-red-800 dark:text-red-200">{error}</p>
          </div>
        )}

        {/* Users Table */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden">
          {loading ? (
            <div className="p-8 text-center text-gray-600 dark:text-gray-400">Loading users...</div>
          ) : users.length === 0 ? (
            <div className="p-8 text-center text-gray-600 dark:text-gray-400">No users found.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
                    <th className="text-left py-3 px-4 text-sm font-semibold text-gray-900 dark:text-gray-100">User</th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-gray-900 dark:text-gray-100">Organization</th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-gray-900 dark:text-gray-100">Role</th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-gray-900 dark:text-gray-100">Auth</th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-gray-900 dark:text-gray-100">Status</th>
                    <th className="text-right py-3 px-4 text-sm font-semibold text-gray-900 dark:text-gray-100">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr
                      key={u.id}
                      className={`border-b border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-900/50 ${
                        !u.is_active ? 'opacity-60' : ''
                      }`}
                    >
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-3">
                          {u.avatar_url ? (
                            <img src={u.avatar_url} alt="" className="w-8 h-8 rounded-full" />
                          ) : (
                            <div className="w-8 h-8 rounded-full bg-gray-200 dark:bg-gray-700 flex items-center justify-center text-gray-500 dark:text-gray-400 text-sm font-medium">
                              {u.email[0].toUpperCase()}
                            </div>
                          )}
                          <div>
                            <div className="font-medium text-gray-900 dark:text-gray-100">
                              {u.full_name || 'No name'}
                              {u.is_global_admin && (
                                <span className="ml-2 px-1.5 py-0.5 text-xs bg-purple-100 dark:bg-purple-900/30 text-purple-900 dark:text-purple-200 rounded">
                                  Admin
                                </span>
                              )}
                            </div>
                            <div className="text-sm text-gray-600 dark:text-gray-400">{u.email}</div>
                          </div>
                        </div>
                      </td>
                      <td className="py-3 px-4 text-sm text-gray-700 dark:text-gray-300">
                        {u.tenant_name || <span className="text-gray-400">—</span>}
                      </td>
                      <td className="py-3 px-4 text-sm text-gray-700 dark:text-gray-300">
                        {u.role_display_name || <span className="text-gray-400">—</span>}
                      </td>
                      <td className="py-3 px-4">
                        <span className={`px-2 py-1 text-xs font-semibold rounded ${
                          u.auth_provider === 'google'
                            ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-900 dark:text-blue-200'
                            : 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100'
                        }`}>
                          {u.auth_provider === 'google' ? 'Google' : 'Local'}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <span className={`px-2 py-1 text-xs font-semibold rounded-full ${
                          u.is_active
                            ? 'bg-green-100 dark:bg-green-900/30 text-green-900 dark:text-green-200'
                            : 'bg-red-100 dark:bg-red-900/30 text-red-900 dark:text-red-200'
                        }`}>
                          {u.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => setEditingUser(u)}
                            className="text-sm text-blue-600 hover:text-blue-800 dark:text-blue-400"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => handleToggleStatus(u)}
                            className="text-sm text-gray-600 hover:text-gray-800 dark:text-gray-400"
                          >
                            {u.is_active ? 'Suspend' : 'Activate'}
                          </button>
                          {!u.is_global_admin && (
                            <>
                              <button
                                onClick={() => handleToggleAdmin(u)}
                                className="text-sm text-purple-600 hover:text-purple-800 dark:text-purple-400"
                              >
                                Make Admin
                              </button>
                              <button
                                onClick={() => handleDelete(u)}
                                className="text-sm text-red-600 hover:text-red-800 dark:text-red-400"
                              >
                                Delete
                              </button>
                            </>
                          )}
                          {u.is_global_admin && user?.id !== u.id && (
                            <button
                              onClick={() => handleToggleAdmin(u)}
                              className="text-sm text-orange-600 hover:text-orange-800 dark:text-orange-400"
                            >
                              Remove Admin
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="px-4 py-3 border-t border-gray-200 dark:border-gray-700 flex items-center justify-between">
              <div className="text-sm text-gray-600 dark:text-gray-400">
                Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, total)} of {total} users
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage(page - 1)}
                  disabled={page === 1}
                  className="px-3 py-1 border dark:border-gray-700 rounded text-sm disabled:opacity-50"
                >
                  Previous
                </button>
                <button
                  onClick={() => setPage(page + 1)}
                  disabled={page >= totalPages}
                  className="px-3 py-1 border dark:border-gray-700 rounded text-sm disabled:opacity-50"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Create User Modal */}
        {showCreateModal && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full">
              <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
                <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">Create User</h2>
                <button onClick={() => setShowCreateModal(false)} className="text-gray-500 hover:text-gray-700">✕</button>
              </div>
              <div className="p-6 space-y-4">
                {modalError && (
                  <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded text-sm text-red-800 dark:text-red-200">
                    {modalError}
                  </div>
                )}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Email</label>
                  <input
                    type="email"
                    value={createForm.email}
                    onChange={(e) => setCreateForm({ ...createForm, email: e.target.value })}
                    className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Password</label>
                  <input
                    type="password"
                    value={createForm.password}
                    onChange={(e) => setCreateForm({ ...createForm, password: e.target.value })}
                    className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700"
                    required
                    minLength={8}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Full Name</label>
                  <input
                    type="text"
                    value={createForm.full_name}
                    onChange={(e) => setCreateForm({ ...createForm, full_name: e.target.value })}
                    className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Organization</label>
                  <select
                    value={createForm.tenant_id}
                    onChange={(e) => setCreateForm({ ...createForm, tenant_id: e.target.value })}
                    className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700"
                    required
                  >
                    <option value="">Select organization...</option>
                    {tenants.map((t) => (
                      <option key={t.id} value={t.id}>{t.name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Role</label>
                  <select
                    value={createForm.role_name}
                    onChange={(e) => setCreateForm({ ...createForm, role_name: e.target.value })}
                    className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700"
                  >
                    <option value="owner">Owner</option>
                    <option value="admin">Admin</option>
                    <option value="member">Member</option>
                    <option value="readonly">Read Only</option>
                  </select>
                </div>
              </div>
              <div className="flex justify-end gap-3 p-6 border-t border-gray-200 dark:border-gray-700">
                <button
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-gray-100 rounded-md"
                >
                  Cancel
                </button>
                <button
                  onClick={handleCreate}
                  disabled={modalLoading || !createForm.email || !createForm.password || !createForm.full_name || !createForm.tenant_id}
                  className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-md disabled:opacity-50"
                >
                  {modalLoading ? 'Creating...' : 'Create User'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Edit User Modal */}
        {editingUser && (
          <EditUserModal
            user={editingUser}
            tenants={tenants}
            onClose={() => setEditingUser(null)}
            onSave={handleUpdate}
            loading={modalLoading}
            error={modalError}
          />
        )}
      </div>
    </div>
  )
}

// Edit User Modal Component
function EditUserModal({
  user,
  tenants,
  onClose,
  onSave,
  loading,
  error,
}: {
  user: GlobalUser
  tenants: TenantInfo[]
  onClose: () => void
  onSave: (updates: UserUpdateRequest) => Promise<void>
  loading: boolean
  error: string | null
}) {
  const [fullName, setFullName] = useState(user.full_name || '')
  const [tenantId, setTenantId] = useState(user.tenant_id || '')
  const [roleName, setRoleName] = useState(user.role || 'member')
  const [isActive, setIsActive] = useState(user.is_active)

  const handleSubmit = () => {
    const updates: UserUpdateRequest = {}
    if (fullName !== user.full_name) updates.full_name = fullName
    if (tenantId !== user.tenant_id) updates.tenant_id = tenantId
    if (roleName !== user.role) updates.role_name = roleName
    if (isActive !== user.is_active) updates.is_active = isActive
    onSave(updates)
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full">
        <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">Edit User</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700">✕</button>
        </div>
        <div className="p-6 space-y-4">
          {error && (
            <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded text-sm text-red-800 dark:text-red-200">
              {error}
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Email</label>
            <input
              type="email"
              value={user.email}
              disabled
              className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-500 bg-gray-100 dark:bg-gray-600"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Full Name</label>
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Organization</label>
            <select
              value={tenantId}
              onChange={(e) => setTenantId(e.target.value)}
              className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700"
            >
              <option value="">No organization</option>
              {tenants.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Role</label>
            <select
              value={roleName}
              onChange={(e) => setRoleName(e.target.value)}
              className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700"
            >
              <option value="owner">Owner</option>
              <option value="admin">Admin</option>
              <option value="member">Member</option>
              <option value="readonly">Read Only</option>
            </select>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="isActive"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              className="rounded"
            />
            <label htmlFor="isActive" className="text-sm text-gray-700 dark:text-gray-300">Active</label>
          </div>
        </div>
        <div className="flex justify-end gap-3 p-6 border-t border-gray-200 dark:border-gray-700">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-gray-100 rounded-md"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-md disabled:opacity-50"
          >
            {loading ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </div>
    </div>
  )
}
