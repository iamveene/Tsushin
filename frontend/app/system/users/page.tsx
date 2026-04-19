'use client'

/**
 * Global Users Management Page (Global Admin Only)
 * Manage users across all tenants
 */

import { useState, useEffect, useCallback } from 'react'
import { useRequireGlobalAdmin } from '@/contexts/AuthContext'
import {
  api,
  GlobalUser,
  GlobalUserStats,
  GlobalInvitation,
  TenantInfo,
  UserCreateRequest,
  UserUpdateRequest,
} from '@/lib/client'
import { copyToClipboard } from '@/lib/clipboard'

// Backend may return either an absolute URL (multi-tenant / tunnel-aware)
// or a legacy relative path. Fall back to the current origin when relative.
function toAbsoluteInviteUrl(link: string): string {
  if (/^https?:\/\//i.test(link)) return link
  if (typeof window === 'undefined') return link
  return `${window.location.origin}${link.startsWith('/') ? link : `/${link}`}`
}

type InviteRole = 'global_admin' | 'owner' | 'admin' | 'member' | 'readonly'
type AuthProvider = 'local' | 'google'

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

  // Invite modal state (platform-wide invitation)
  const [showInviteModal, setShowInviteModal] = useState(false)
  const [inviteForm, setInviteForm] = useState<{
    email: string
    role: InviteRole
    tenant_id: string
    auth_provider: AuthProvider
    message: string
  }>({
    email: '',
    role: 'member',
    tenant_id: '',
    auth_provider: 'local',
    message: '',
  })
  const [inviteLoading, setInviteLoading] = useState(false)
  const [inviteError, setInviteError] = useState<string | null>(null)
  const [inviteSuccessLink, setInviteSuccessLink] = useState<string | null>(null)

  // Pending invitations state
  const [invitations, setInvitations] = useState<GlobalInvitation[]>([])
  const [invitationsTotal, setInvitationsTotal] = useState(0)
  const [invitationsLoading, setInvitationsLoading] = useState(false)
  const [invitationsError, setInvitationsError] = useState<string | null>(null)
  const [showInvitations, setShowInvitations] = useState(true)

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
      setUsers(response.items)
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
      setTenants(tenantsRes.items)
    } catch (err) {
      console.error('Failed to fetch stats/tenants:', err)
    }
  }, [])

  // Fetch pending invitations
  const fetchInvitations = useCallback(async () => {
    setInvitationsLoading(true)
    setInvitationsError(null)
    try {
      const resp = await api.getGlobalInvitations({ page: 1, page_size: 100 })
      setInvitations(resp.invitations)
      setInvitationsTotal(resp.total)
    } catch (err: any) {
      console.error('Failed to fetch invitations:', err)
      setInvitationsError(err.message || 'Failed to load invitations')
    } finally {
      setInvitationsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!authLoading && user) {
      fetchUsers()
      fetchStatsAndTenants()
      fetchInvitations()
    }
  }, [fetchUsers, fetchStatsAndTenants, fetchInvitations, authLoading, user])

  // Reset page when filters change
  useEffect(() => {
    setPage(1)
  }, [search, tenantFilter, statusFilter, authFilter, adminFilter])

  // Listen for global refresh events
  useEffect(() => {
    const handleRefresh = () => {
      fetchUsers()
      fetchStatsAndTenants()
      fetchInvitations()
    }
    window.addEventListener('tsushin:refresh', handleRefresh)
    return () => window.removeEventListener('tsushin:refresh', handleRefresh)
  }, [fetchUsers, fetchStatsAndTenants, fetchInvitations])

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

  // Handle invite submit
  const handleInviteSubmit = async () => {
    setInviteLoading(true)
    setInviteError(null)
    setInviteSuccessLink(null)
    try {
      const isGlobal = inviteForm.role === 'global_admin'
      const resp = await api.inviteGlobalUser({
        email: inviteForm.email.trim(),
        tenant_id: isGlobal ? null : inviteForm.tenant_id || null,
        role: isGlobal ? null : inviteForm.role,
        is_global_admin: isGlobal,
        auth_provider: inviteForm.auth_provider,
        message: inviteForm.message.trim() || undefined,
      })
      setInviteSuccessLink(resp.invitation_link ? toAbsoluteInviteUrl(resp.invitation_link) : null)
      fetchInvitations()
    } catch (err: any) {
      setInviteError(err.message || 'Failed to send invitation')
    } finally {
      setInviteLoading(false)
    }
  }

  const resetInviteForm = () => {
    setInviteForm({
      email: '',
      role: 'member',
      tenant_id: '',
      auth_provider: 'local',
      message: '',
    })
    setInviteError(null)
    setInviteSuccessLink(null)
  }

  const handleInviteCancel = async (invitationId: number, email: string) => {
    if (!confirm(`Cancel the pending invitation for ${email}?`)) return
    try {
      await api.cancelGlobalInvitation(invitationId)
      fetchInvitations()
    } catch (err: any) {
      alert(err.message || 'Failed to cancel invitation')
    }
  }

  const formatDate = (iso: string) => {
    try {
      return new Date(iso).toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      })
    } catch {
      return iso
    }
  }

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-tsushin-slate">Loading...</div>
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
              <h1 className="text-3xl font-bold text-white">
                User Management
              </h1>
              <span className="px-3 py-1 bg-purple-100 dark:bg-purple-900/30 text-purple-900 dark:text-purple-200 text-sm font-semibold rounded-full">
                Global Admin
              </span>
            </div>
            <p className="text-tsushin-slate">
              Manage users across all organizations
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => { resetInviteForm(); setShowInviteModal(true) }}
              className="btn-primary px-4 py-2 font-medium rounded-md transition-colors"
            >
              + Invite User
            </button>
            <button
              onClick={() => setShowCreateModal(true)}
              className="px-4 py-2 font-medium rounded-md bg-tsushin-elevated hover:bg-tsushin-surface text-white border border-tsushin-border transition-colors"
              title="Create a user directly (break-glass / admin bootstrap)"
            >
              + Create User
            </button>
          </div>
        </div>

        {/* Stats */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
            <div className="bg-tsushin-surface rounded-xl border border-tsushin-border p-4">
              <div className="text-sm text-tsushin-slate">Total Users</div>
              <div className="text-2xl font-bold text-white">{stats.total_users}</div>
            </div>
            <div className="bg-tsushin-surface rounded-xl border border-tsushin-border p-4">
              <div className="text-sm text-tsushin-slate">Active</div>
              <div className="text-2xl font-bold text-green-600">{stats.active_users}</div>
            </div>
            <div className="bg-tsushin-surface rounded-xl border border-tsushin-border p-4">
              <div className="text-sm text-tsushin-slate">Global Admins</div>
              <div className="text-2xl font-bold text-purple-600">{stats.global_admins}</div>
            </div>
            <div className="bg-tsushin-surface rounded-xl border border-tsushin-border p-4">
              <div className="text-sm text-tsushin-slate">Google SSO</div>
              <div className="text-2xl font-bold text-blue-600">{stats.google_sso_users}</div>
            </div>
            <div className="bg-tsushin-surface rounded-xl border border-tsushin-border p-4">
              <div className="text-sm text-tsushin-slate">Local Auth</div>
              <div className="text-2xl font-bold text-gray-600">{stats.local_users}</div>
            </div>
          </div>
        )}

        {/* Filters */}
        <div className="bg-tsushin-surface rounded-xl border border-tsushin-border p-4 mb-6">
          <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
            <input
              type="text"
              placeholder="Search by email or name..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-elevated"
            />
            <select
              value={tenantFilter}
              onChange={(e) => setTenantFilter(e.target.value)}
              className="px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-elevated"
            >
              <option value="">All Organizations</option>
              {tenants.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as any)}
              className="px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-elevated"
            >
              <option value="all">All Status</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
            <select
              value={authFilter}
              onChange={(e) => setAuthFilter(e.target.value as any)}
              className="px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-elevated"
            >
              <option value="">All Auth Methods</option>
              <option value="local">Local</option>
              <option value="google">Google SSO</option>
            </select>
            <select
              value={adminFilter}
              onChange={(e) => setAdminFilter(e.target.value as any)}
              className="px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-elevated"
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
        <div className="bg-tsushin-surface rounded-xl border border-tsushin-border overflow-hidden">
          {loading ? (
            <div className="p-8 text-center text-tsushin-slate">Loading users...</div>
          ) : users.length === 0 ? (
            <div className="p-8 text-center text-tsushin-slate">No users found.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="bg-tsushin-ink border-b border-tsushin-border">
                    <th className="text-left py-3 px-4 text-sm font-semibold text-white">User</th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-white">Organization</th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-white">Role</th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-white">Auth</th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-white">Status</th>
                    <th className="text-right py-3 px-4 text-sm font-semibold text-white">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr
                      key={u.id}
                      className={`border-b border-tsushin-border hover:bg-tsushin-surface ${
                        !u.is_active ? 'opacity-60' : ''
                      }`}
                    >
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-3">
                          {u.avatar_url ? (
                            <img src={u.avatar_url} alt="" className="w-8 h-8 rounded-full" />
                          ) : (
                            <div className="w-8 h-8 rounded-full bg-tsushin-elevated flex items-center justify-center text-tsushin-muted text-sm font-medium">
                              {u.email[0].toUpperCase()}
                            </div>
                          )}
                          <div>
                            <div className="font-medium text-white">
                              {u.full_name || 'No name'}
                              {u.is_global_admin && (
                                <span className="ml-2 px-1.5 py-0.5 text-xs bg-purple-100 dark:bg-purple-900/30 text-purple-900 dark:text-purple-200 rounded">
                                  Admin
                                </span>
                              )}
                            </div>
                            <div className="text-sm text-tsushin-slate">{u.email}</div>
                          </div>
                        </div>
                      </td>
                      <td className="py-3 px-4 text-sm text-tsushin-fog">
                        {u.tenant_name || <span className="text-gray-400">—</span>}
                      </td>
                      <td className="py-3 px-4 text-sm text-tsushin-fog">
                        {u.role_display_name || <span className="text-gray-400">—</span>}
                      </td>
                      <td className="py-3 px-4">
                        <span className={`px-2 py-1 text-xs font-semibold rounded ${
                          u.auth_provider === 'google'
                            ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-900 dark:text-blue-200'
                            : 'bg-tsushin-elevated text-white'
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
                            className="text-sm text-teal-400 hover:text-teal-300"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => handleToggleStatus(u)}
                            className="text-sm text-tsushin-slate hover:text-white"
                          >
                            {u.is_active ? 'Suspend' : 'Activate'}
                          </button>
                          {!u.is_global_admin && (
                            <>
                              <button
                                onClick={() => handleToggleAdmin(u)}
                                className="text-sm text-teal-400 hover:text-teal-300"
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
            <div className="px-4 py-3 border-t border-tsushin-border flex items-center justify-between">
              <div className="text-sm text-tsushin-slate">
                Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, total)} of {total} users
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage(page - 1)}
                  disabled={page === 1}
                  className="px-3 py-1 border border-tsushin-border rounded text-sm disabled:opacity-50"
                >
                  Previous
                </button>
                <button
                  onClick={() => setPage(page + 1)}
                  disabled={page >= totalPages}
                  className="px-3 py-1 border border-tsushin-border rounded text-sm disabled:opacity-50"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Pending Invitations */}
        <div className="mt-8 bg-tsushin-surface rounded-xl border border-tsushin-border overflow-hidden">
          <button
            type="button"
            onClick={() => setShowInvitations((v) => !v)}
            className="w-full px-4 py-3 flex items-center justify-between bg-tsushin-ink border-b border-tsushin-border hover:bg-tsushin-elevated/40 transition-colors"
          >
            <div className="flex items-center gap-3">
              <svg
                className={`w-4 h-4 text-tsushin-slate transition-transform ${showInvitations ? 'rotate-90' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
              <span className="text-sm font-semibold text-white">Pending Invitations</span>
              <span className="px-2 py-0.5 text-xs bg-tsushin-elevated text-tsushin-slate rounded-full">
                {invitationsTotal}
              </span>
            </div>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); fetchInvitations() }}
              className="text-xs text-teal-400 hover:text-teal-300"
            >
              Refresh
            </button>
          </button>

          {showInvitations && (
            <>
              {invitationsError && (
                <div className="p-4 bg-red-50 dark:bg-red-900/20 border-b border-red-200 dark:border-red-800 text-sm text-red-800 dark:text-red-200">
                  {invitationsError}
                </div>
              )}
              {invitationsLoading ? (
                <div className="p-8 text-center text-tsushin-slate">Loading invitations...</div>
              ) : invitations.length === 0 ? (
                <div className="p-8 text-center text-tsushin-slate">No pending invitations.</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="bg-tsushin-ink border-b border-tsushin-border">
                        <th className="text-left py-3 px-4 text-sm font-semibold text-white">Email</th>
                        <th className="text-left py-3 px-4 text-sm font-semibold text-white">Scope</th>
                        <th className="text-left py-3 px-4 text-sm font-semibold text-white">Role</th>
                        <th className="text-left py-3 px-4 text-sm font-semibold text-white">Auth</th>
                        <th className="text-left py-3 px-4 text-sm font-semibold text-white">Invited By</th>
                        <th className="text-left py-3 px-4 text-sm font-semibold text-white">Expires</th>
                        <th className="text-right py-3 px-4 text-sm font-semibold text-white">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {invitations.map((inv) => (
                        <tr key={inv.id} className="border-b border-tsushin-border hover:bg-tsushin-elevated/30">
                          <td className="py-3 px-4 text-sm text-white">{inv.email}</td>
                          <td className="py-3 px-4 text-sm">
                            {inv.is_global_admin ? (
                              <span className="px-2 py-0.5 text-xs bg-purple-500/20 text-purple-300 rounded-full border border-purple-500/30">
                                Global
                              </span>
                            ) : (
                              <span className="text-tsushin-fog">{inv.tenant_name || '—'}</span>
                            )}
                          </td>
                          <td className="py-3 px-4 text-sm text-tsushin-fog">
                            {inv.is_global_admin ? 'Global Admin' : (inv.role_display_name || '—')}
                          </td>
                          <td className="py-3 px-4">
                            <span className={`px-2 py-1 text-xs font-semibold rounded ${
                              inv.auth_provider === 'google'
                                ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-900 dark:text-blue-200'
                                : 'bg-tsushin-elevated text-white'
                            }`}>
                              {inv.auth_provider === 'google' ? 'Google' : 'Local'}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-sm text-tsushin-fog">{inv.invited_by_name}</td>
                          <td className="py-3 px-4 text-sm text-tsushin-slate">{formatDate(inv.expires_at)}</td>
                          <td className="py-3 px-4 text-right">
                            <button
                              onClick={() => handleInviteCancel(inv.id, inv.email)}
                              className="text-sm text-red-600 hover:text-red-800 dark:text-red-400"
                            >
                              Cancel
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </div>

        {/* Invite User Modal */}
        {showInviteModal && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-tsushin-surface rounded-xl border border-tsushin-border shadow-xl max-w-lg w-full">
              <div className="flex items-center justify-between p-6 border-b border-tsushin-border">
                <h2 className="text-xl font-bold text-white">Invite User</h2>
                <button
                  onClick={() => { setShowInviteModal(false); resetInviteForm() }}
                  className="text-tsushin-muted hover:text-white"
                >
                  ✕
                </button>
              </div>

              {inviteSuccessLink ? (
                <div className="p-6 space-y-4">
                  <div className="p-4 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
                    <h3 className="text-sm font-semibold text-green-900 dark:text-green-100 mb-1">
                      ✓ Invitation Sent
                    </h3>
                    <p className="text-sm text-green-800 dark:text-green-200">
                      An invitation was sent to <strong>{inviteForm.email}</strong>.
                    </p>
                  </div>
                  <div className="bg-tsushin-ink rounded-md p-4">
                    <label className="block text-xs font-medium text-tsushin-slate uppercase tracking-wider mb-2">
                      Invitation Link
                    </label>
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        readOnly
                        value={inviteSuccessLink}
                        className="flex-1 px-3 py-2 border border-tsushin-border rounded-md text-sm text-white bg-tsushin-elevated"
                      />
                      <button
                        onClick={() => {
                          copyToClipboard(inviteSuccessLink)
                          alert('Link copied!')
                        }}
                        className="px-3 py-2 bg-teal-600 hover:bg-teal-700 text-white text-sm font-medium rounded-md"
                      >
                        Copy
                      </button>
                    </div>
                    <p className="text-xs text-tsushin-slate mt-2">Expires in 7 days.</p>
                  </div>
                  <div className="flex justify-end gap-3 pt-2">
                    <button
                      onClick={() => { resetInviteForm() }}
                      className="px-4 py-2 bg-tsushin-elevated hover:bg-tsushin-surface text-white rounded-md border border-tsushin-border"
                    >
                      Invite Another
                    </button>
                    <button
                      onClick={() => { setShowInviteModal(false); resetInviteForm() }}
                      className="btn-primary px-4 py-2 rounded-md"
                    >
                      Done
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="p-6 space-y-4">
                    {inviteError && (
                      <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded text-sm text-red-800 dark:text-red-200">
                        {inviteError}
                      </div>
                    )}
                    <div>
                      <label className="block text-sm font-medium text-tsushin-fog mb-1">Email</label>
                      <input
                        type="email"
                        value={inviteForm.email}
                        onChange={(e) => setInviteForm({ ...inviteForm, email: e.target.value })}
                        className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-elevated"
                        required
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-tsushin-fog mb-1">Role</label>
                      <select
                        value={inviteForm.role}
                        onChange={(e) => setInviteForm({ ...inviteForm, role: e.target.value as InviteRole })}
                        className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-elevated"
                      >
                        <option value="global_admin">Global Admin</option>
                        <option value="owner">Owner</option>
                        <option value="admin">Admin</option>
                        <option value="member">Member</option>
                        <option value="readonly">Read-Only</option>
                      </select>
                    </div>

                    {inviteForm.role !== 'global_admin' && (
                      <div>
                        <label className="block text-sm font-medium text-tsushin-fog mb-1">Organization</label>
                        <select
                          value={inviteForm.tenant_id}
                          onChange={(e) => setInviteForm({ ...inviteForm, tenant_id: e.target.value })}
                          className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-elevated"
                          required
                        >
                          <option value="">Select organization...</option>
                          {tenants.map((t) => (
                            <option key={t.id} value={t.id}>{t.name}</option>
                          ))}
                        </select>
                      </div>
                    )}

                    <div>
                      <label className="block text-sm font-medium text-tsushin-fog mb-2">Sign-in method</label>
                      <div className="space-y-2">
                        <label className="flex items-start gap-3 p-3 border border-tsushin-border rounded-md cursor-pointer hover:bg-tsushin-elevated/50 transition-colors">
                          <input
                            type="radio"
                            name="invite-auth"
                            value="local"
                            checked={inviteForm.auth_provider === 'local'}
                            onChange={() => setInviteForm({ ...inviteForm, auth_provider: 'local' })}
                            className="mt-1"
                          />
                          <div className="flex-1">
                            <div className="text-sm font-medium text-white">Local password</div>
                            <div className="text-xs text-tsushin-slate">User creates a password on accept.</div>
                          </div>
                        </label>
                        <label className="flex items-start gap-3 p-3 border border-tsushin-border rounded-md cursor-pointer hover:bg-tsushin-elevated/50 transition-colors">
                          <input
                            type="radio"
                            name="invite-auth"
                            value="google"
                            checked={inviteForm.auth_provider === 'google'}
                            onChange={() => setInviteForm({ ...inviteForm, auth_provider: 'google' })}
                            className="mt-1"
                          />
                          <div className="flex-1">
                            <div className="text-sm font-medium text-white">Google SSO</div>
                            <div className="text-xs text-tsushin-slate">User must accept via Google with the matching email.</div>
                          </div>
                        </label>
                      </div>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-tsushin-fog mb-1">
                        Personal Message (Optional)
                      </label>
                      <textarea
                        value={inviteForm.message}
                        onChange={(e) => setInviteForm({ ...inviteForm, message: e.target.value })}
                        rows={3}
                        className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-elevated"
                      />
                    </div>
                  </div>
                  <div className="flex justify-end gap-3 p-6 border-t border-tsushin-border">
                    <button
                      onClick={() => { setShowInviteModal(false); resetInviteForm() }}
                      className="px-4 py-2 bg-tsushin-elevated hover:bg-tsushin-surface text-white rounded-md border border-tsushin-border"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleInviteSubmit}
                      disabled={
                        inviteLoading
                        || !inviteForm.email
                        || (inviteForm.role !== 'global_admin' && !inviteForm.tenant_id)
                      }
                      className="btn-primary px-4 py-2 rounded-md disabled:opacity-50"
                    >
                      {inviteLoading ? 'Sending...' : 'Send Invitation'}
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        )}

        {/* Create User Modal */}
        {showCreateModal && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-tsushin-surface rounded-xl border border-tsushin-border shadow-xl max-w-md w-full">
              <div className="flex items-center justify-between p-6 border-b border-tsushin-border">
                <h2 className="text-xl font-bold text-white">Create User</h2>
                <button onClick={() => setShowCreateModal(false)} className="text-tsushin-muted hover:text-white">✕</button>
              </div>
              <div className="p-6 space-y-4">
                {modalError && (
                  <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded text-sm text-red-800 dark:text-red-200">
                    {modalError}
                  </div>
                )}
                <div>
                  <label className="block text-sm font-medium text-tsushin-fog mb-1">Email</label>
                  <input
                    type="email"
                    value={createForm.email}
                    onChange={(e) => setCreateForm({ ...createForm, email: e.target.value })}
                    className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-elevated"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-tsushin-fog mb-1">Password</label>
                  <input
                    type="password"
                    value={createForm.password}
                    onChange={(e) => setCreateForm({ ...createForm, password: e.target.value })}
                    className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-elevated"
                    required
                    minLength={6}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-tsushin-fog mb-1">Full Name</label>
                  <input
                    type="text"
                    value={createForm.full_name}
                    onChange={(e) => setCreateForm({ ...createForm, full_name: e.target.value })}
                    className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-elevated"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-tsushin-fog mb-1">Organization</label>
                  <select
                    value={createForm.tenant_id}
                    onChange={(e) => setCreateForm({ ...createForm, tenant_id: e.target.value })}
                    className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-elevated"
                    required
                  >
                    <option value="">Select organization...</option>
                    {tenants.map((t) => (
                      <option key={t.id} value={t.id}>{t.name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-tsushin-fog mb-1">Role</label>
                  <select
                    value={createForm.role_name}
                    onChange={(e) => setCreateForm({ ...createForm, role_name: e.target.value })}
                    className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-elevated"
                  >
                    <option value="owner">Owner</option>
                    <option value="admin">Admin</option>
                    <option value="member">Member</option>
                    <option value="readonly">Read Only</option>
                  </select>
                </div>
              </div>
              <div className="flex justify-end gap-3 p-6 border-t border-tsushin-border">
                <button
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 bg-tsushin-elevated text-white rounded-md"
                >
                  Cancel
                </button>
                <button
                  onClick={handleCreate}
                  disabled={modalLoading || !createForm.email || !createForm.password || !createForm.full_name || !createForm.tenant_id}
                  className="btn-primary px-4 py-2 rounded-md disabled:opacity-50"
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
      <div className="bg-tsushin-surface rounded-xl border border-tsushin-border shadow-xl max-w-md w-full">
        <div className="flex items-center justify-between p-6 border-b border-tsushin-border">
          <h2 className="text-xl font-bold text-white">Edit User</h2>
          <button onClick={onClose} className="text-tsushin-muted hover:text-white">✕</button>
        </div>
        <div className="p-6 space-y-4">
          {error && (
            <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded text-sm text-red-800 dark:text-red-200">
              {error}
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-tsushin-fog mb-1">Email</label>
            <input
              type="email"
              value={user.email}
              disabled
              className="w-full px-3 py-2 border border-tsushin-border rounded-md text-tsushin-muted bg-tsushin-elevated"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-tsushin-fog mb-1">Full Name</label>
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-elevated"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-tsushin-fog mb-1">Organization</label>
            <select
              value={tenantId}
              onChange={(e) => setTenantId(e.target.value)}
              className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-elevated"
            >
              <option value="">No organization</option>
              {tenants.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-tsushin-fog mb-1">Role</label>
            <select
              value={roleName}
              onChange={(e) => setRoleName(e.target.value)}
              className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-elevated"
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
            <label htmlFor="isActive" className="text-sm text-tsushin-fog">Active</label>
          </div>
        </div>
        <div className="flex justify-end gap-3 p-6 border-t border-tsushin-border">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-tsushin-elevated text-white rounded-md"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="btn-primary px-4 py-2 rounded-md disabled:opacity-50"
          >
            {loading ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </div>
    </div>
  )
}
