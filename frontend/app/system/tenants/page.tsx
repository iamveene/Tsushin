'use client'

/**
 * Tenant Management Page (Global Admin Only)
 * Manages all tenants on the platform
 * Phase 7.9: Connected to real API
 */

import { useState, useEffect, useCallback } from 'react'
import { useRequireGlobalAdmin } from '@/contexts/AuthContext'
import { api, TenantInfo } from '@/lib/client'
import { GlobeIcon } from '@/components/ui/icons'

export default function TenantsPage() {
  const { user, loading: authLoading } = useRequireGlobalAdmin()
  const [tenants, setTenants] = useState<TenantInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [filterStatus, setFilterStatus] = useState('all')
  const [filterPlan, setFilterPlan] = useState('all')
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [createLoading, setCreateLoading] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [newTenant, setNewTenant] = useState({
    name: '',
    owner_email: '',
    owner_password: '',
    owner_name: '',
    plan: 'free',
  })

  // Edit tenant state
  const [showEditModal, setShowEditModal] = useState(false)
  const [editLoading, setEditLoading] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)
  const [editingTenant, setEditingTenant] = useState<TenantInfo | null>(null)
  const [editForm, setEditForm] = useState({
    name: '',
    plan: 'free',
    max_users: 5,
    max_agents: 5,
    max_monthly_requests: 10000,
    status: 'active',
  })

  // Pagination
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const pageSize = 20

  // Fetch tenants
  const fetchTenants = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await api.getTenants({
        page,
        page_size: pageSize,
        search: searchQuery || undefined,
        status: filterStatus !== 'all' ? filterStatus : undefined,
        plan: filterPlan !== 'all' ? filterPlan : undefined,
      })
      setTenants(response.tenants)
      setTotal(response.total)
    } catch (err) {
      console.error('Failed to fetch tenants:', err)
      setError('Failed to load tenants')
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, searchQuery, filterStatus, filterPlan])

  useEffect(() => {
    if (!authLoading && user) {
      fetchTenants()
    }
  }, [fetchTenants, authLoading, user])

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => {
      setPage(1)
      fetchTenants()
    }, 300)
    return () => clearTimeout(timer)
  }, [searchQuery])

  // Listen for global refresh events
  useEffect(() => {
    const handleRefresh = () => {
      fetchTenants()
    }
    window.addEventListener('tsushin:refresh', handleRefresh)
    return () => window.removeEventListener('tsushin:refresh', handleRefresh)
  }, [fetchTenants])

  const handleCreateTenant = async (e: React.FormEvent) => {
    e.preventDefault()
    setCreateLoading(true)
    setCreateError(null)

    try {
      await api.createTenant({
        name: newTenant.name,
        owner_email: newTenant.owner_email,
        owner_password: newTenant.owner_password,
        owner_name: newTenant.owner_name,
        plan: newTenant.plan,
      })
      setShowCreateModal(false)
      setNewTenant({
        name: '',
        owner_email: '',
        owner_password: '',
        owner_name: '',
        plan: 'free',
      })
      fetchTenants()
    } catch (err: any) {
      setCreateError(err.message || 'Failed to create tenant')
    } finally {
      setCreateLoading(false)
    }
  }

  const handleOpenEdit = (tenant: TenantInfo) => {
    setEditingTenant(tenant)
    setEditForm({
      name: tenant.name,
      plan: tenant.plan,
      max_users: tenant.max_users,
      max_agents: tenant.max_agents,
      max_monthly_requests: tenant.max_monthly_requests,
      status: tenant.status,
    })
    setEditError(null)
    setShowEditModal(true)
  }

  const handleUpdateTenant = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editingTenant) return
    setEditLoading(true)
    setEditError(null)
    try {
      await api.updateTenant(editingTenant.id, {
        name: editForm.name,
        plan: editForm.plan,
        max_users: editForm.max_users,
        max_agents: editForm.max_agents,
        max_monthly_requests: editForm.max_monthly_requests,
        status: editForm.status,
      })
      setShowEditModal(false)
      setEditingTenant(null)
      fetchTenants()
    } catch (err: any) {
      setEditError(err.message || 'Failed to update tenant')
    } finally {
      setEditLoading(false)
    }
  }

  const handleDeleteTenant = async (tenantId: string) => {
    if (!confirm('Are you sure you want to delete this tenant? This action cannot be undone.'))
      return

    try {
      await api.deleteTenant(tenantId)
      fetchTenants()
    } catch (err: any) {
      alert(err.message || 'Failed to delete tenant')
    }
  }

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-tsushin-slate">Loading...</div>
      </div>
    )
  }

  // Calculate stats
  const stats = {
    total: total,
    active: tenants.filter((t) => t.status === 'active').length,
    trial: tenants.filter((t) => t.status === 'trial').length,
    suspended: tenants.filter((t) => t.status === 'suspended').length,
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <div className="flex items-center space-x-3 mb-2">
              <h1 className="text-3xl font-bold text-white">
                Tenant Management
              </h1>
              <span className="px-3 py-1 bg-purple-100 dark:bg-purple-900/30 text-purple-900 dark:text-purple-200 text-sm font-semibold rounded-full inline-flex items-center gap-1">
                <GlobeIcon size={14} /> Global Admin
              </span>
            </div>
            <p className="text-tsushin-slate">
              Manage all organizations on the platform
            </p>
          </div>

          <button
            onClick={() => setShowCreateModal(true)}
            className="btn-primary px-4 py-2 font-medium rounded-md transition-colors"
          >
            + Create Tenant
          </button>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-6">
          <div className="bg-tsushin-surface rounded-xl border border-tsushin-border p-6">
            <div className="text-sm text-tsushin-slate mb-1">Total Tenants</div>
            <div className="text-3xl font-bold text-white">{stats.total}</div>
          </div>
          <div className="bg-tsushin-surface rounded-xl border border-tsushin-border p-6">
            <div className="text-sm text-tsushin-slate mb-1">Active</div>
            <div className="text-3xl font-bold text-green-600 dark:text-green-400">
              {stats.active}
            </div>
          </div>
          <div className="bg-tsushin-surface rounded-xl border border-tsushin-border p-6">
            <div className="text-sm text-tsushin-slate mb-1">Trial</div>
            <div className="text-3xl font-bold text-yellow-600 dark:text-yellow-400">
              {stats.trial}
            </div>
          </div>
          <div className="bg-tsushin-surface rounded-xl border border-tsushin-border p-6">
            <div className="text-sm text-tsushin-slate mb-1">Suspended</div>
            <div className="text-3xl font-bold text-red-600 dark:text-red-400">
              {stats.suspended}
            </div>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-6 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
            <p className="text-sm text-red-800 dark:text-red-200">{error}</p>
            <button
              onClick={fetchTenants}
              className="mt-2 text-sm text-red-600 hover:underline"
            >
              Retry
            </button>
          </div>
        )}

        {/* Filters */}
        <div className="bg-tsushin-surface rounded-xl border border-tsushin-border p-6 mb-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

            <div>
              <label className="block text-sm font-medium text-white mb-2">
                Search Tenants
              </label>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search by name or slug..."
                className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface focus:ring-2 focus:ring-teal-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-white mb-2">
                Filter by Status
              </label>
              <select
                value={filterStatus}
                onChange={(e) => {
                  setFilterStatus(e.target.value)
                  setPage(1)
                }}
                className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface"
              >
                <option value="all">All Status</option>
                <option value="active">Active</option>
                <option value="trial">Trial</option>
                <option value="suspended">Suspended</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-white mb-2">
                Filter by Plan
              </label>
              <select
                value={filterPlan}
                onChange={(e) => {
                  setFilterPlan(e.target.value)
                  setPage(1)
                }}
                className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface"
              >
                <option value="all">All Plans</option>
                <option value="free">Free</option>
                <option value="pro">Pro</option>
                <option value="team">Team</option>
                <option value="enterprise">Enterprise</option>
              </select>
            </div>
          </div>
        </div>

        {/* Tenants Table */}
        <div className="bg-tsushin-surface rounded-xl border border-tsushin-border overflow-hidden">
          {loading ? (
            <div className="p-8 text-center text-tsushin-slate">
              Loading tenants...
            </div>
          ) : tenants.length === 0 ? (
            <div className="p-8 text-center text-tsushin-slate">
              No tenants found matching your filters.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="bg-tsushin-ink border-b border-tsushin-border">
                    <th className="text-left py-3 px-4 text-sm font-semibold text-white">
                      Organization
                    </th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-white">
                      Plan
                    </th>
                    <th className="text-center py-3 px-4 text-sm font-semibold text-white">
                      Users
                    </th>
                    <th className="text-center py-3 px-4 text-sm font-semibold text-white">
                      Agents
                    </th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-white">
                      Status
                    </th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-white">
                      Created
                    </th>
                    <th className="text-right py-3 px-4 text-sm font-semibold text-white">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {tenants.map((tenant) => (
                    <tr
                      key={tenant.id}
                      className="border-b border-tsushin-border hover:bg-tsushin-surface"
                    >
                      <td className="py-3 px-4">
                        <div>
                          <div className="font-medium text-white">
                            {tenant.name}
                          </div>
                          <div className="text-sm text-tsushin-slate">
                            {tenant.slug}
                          </div>
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <span className="px-2 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-900 dark:text-blue-200 text-xs font-semibold rounded">
                          {tenant.plan}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-center text-sm text-tsushin-fog">
                        {tenant.user_count} / {tenant.max_users}
                      </td>
                      <td className="py-3 px-4 text-center text-sm text-tsushin-fog">
                        {tenant.agent_count} / {tenant.max_agents}
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`px-2 py-1 text-xs font-semibold rounded-full ${
                            tenant.status === 'active'
                              ? 'bg-green-100 dark:bg-green-900/30 text-green-900 dark:text-green-200'
                              : tenant.status === 'trial'
                              ? 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-900 dark:text-yellow-200'
                              : 'bg-red-100 dark:bg-red-900/30 text-red-900 dark:text-red-200'
                          }`}
                        >
                          {tenant.status.toUpperCase()}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-sm text-tsushin-fog">
                        {tenant.created_at
                          ? new Date(tenant.created_at).toLocaleDateString()
                          : 'N/A'}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <button
                          onClick={() => handleOpenEdit(tenant)}
                          className="text-sm text-teal-400 hover:underline mr-3"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => handleDeleteTenant(tenant.id)}
                          className="text-sm text-red-600 dark:text-red-400 hover:underline"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {total > pageSize && (
            <div className="flex items-center justify-between p-4 border-t border-tsushin-border">
              <div className="text-sm text-tsushin-slate">
                Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, total)} of{' '}
                {total} tenants
              </div>
              <div className="flex space-x-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="px-3 py-1 bg-tsushin-elevated rounded disabled:opacity-50"
                >
                  Previous
                </button>
                <button
                  onClick={() => setPage((p) => p + 1)}
                  disabled={page * pageSize >= total}
                  className="px-3 py-1 bg-tsushin-elevated rounded disabled:opacity-50"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Edit Tenant Modal */}
        {showEditModal && editingTenant && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-tsushin-surface rounded-xl border border-tsushin-border shadow-xl max-w-2xl w-full">
              <div className="flex items-center justify-between p-6 border-b border-tsushin-border">
                <h2 className="text-xl font-bold text-white">
                  Edit Tenant: {editingTenant.name}
                </h2>
                <button
                  onClick={() => setShowEditModal(false)}
                  className="p-2 text-tsushin-slate hover:text-white"
                >
                  ✕
                </button>
              </div>

              <form onSubmit={handleUpdateTenant}>
                <div className="p-6 space-y-4">
                  {editError && (
                    <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded text-sm text-red-800 dark:text-red-200">
                      {editError}
                    </div>
                  )}

                  <div>
                    <label className="block text-sm font-medium text-white mb-2">
                      Organization Name
                    </label>
                    <input
                      type="text"
                      value={editForm.name}
                      onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                      required
                      className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-white mb-2">
                        Plan
                      </label>
                      <select
                        value={editForm.plan}
                        onChange={(e) => setEditForm({ ...editForm, plan: e.target.value })}
                        className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface"
                      >
                        <option value="free">Free</option>
                        <option value="pro">Pro</option>
                        <option value="team">Team</option>
                        <option value="enterprise">Enterprise</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-white mb-2">
                        Status
                      </label>
                      <select
                        value={editForm.status}
                        onChange={(e) => setEditForm({ ...editForm, status: e.target.value })}
                        className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface"
                      >
                        <option value="active">Active</option>
                        <option value="trial">Trial</option>
                        <option value="suspended">Suspended</option>
                      </select>
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-white mb-2">
                        Max Users
                      </label>
                      <input
                        type="number"
                        min={1}
                        value={editForm.max_users}
                        onChange={(e) => setEditForm({ ...editForm, max_users: parseInt(e.target.value) || 1 })}
                        className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface"
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-white mb-2">
                        Max Agents
                      </label>
                      <input
                        type="number"
                        min={1}
                        value={editForm.max_agents}
                        onChange={(e) => setEditForm({ ...editForm, max_agents: parseInt(e.target.value) || 1 })}
                        className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface"
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-white mb-2">
                        Monthly Request Limit
                      </label>
                      <input
                        type="number"
                        min={1}
                        value={editForm.max_monthly_requests}
                        onChange={(e) => setEditForm({ ...editForm, max_monthly_requests: parseInt(e.target.value) || 1 })}
                        className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface"
                      />
                    </div>
                  </div>

                  <div className="text-xs text-tsushin-slate bg-tsushin-ink rounded p-3">
                    Current usage: <span className="text-white font-medium">{editingTenant.user_count}</span> / {editingTenant.max_users} users
                    &nbsp;&bull;&nbsp;
                    <span className="text-white font-medium">{editingTenant.agent_count}</span> / {editingTenant.max_agents} agents
                  </div>
                </div>

                <div className="flex justify-end space-x-3 p-6 border-t border-tsushin-border">
                  <button
                    type="button"
                    onClick={() => setShowEditModal(false)}
                    className="px-4 py-2 bg-tsushin-elevated text-white rounded-md"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={editLoading}
                    className="btn-primary px-4 py-2 rounded-md disabled:opacity-50"
                  >
                    {editLoading ? 'Saving...' : 'Save Changes'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Create Tenant Modal */}
        {showCreateModal && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-tsushin-surface rounded-xl border border-tsushin-border shadow-xl max-w-2xl w-full">
              <div className="flex items-center justify-between p-6 border-b border-tsushin-border">
                <h2 className="text-xl font-bold text-white">
                  Create New Tenant
                </h2>
                <button
                  onClick={() => setShowCreateModal(false)}
                  className="p-2 text-tsushin-slate hover:text-white"
                >
                  ✕
                </button>
              </div>

              <form onSubmit={handleCreateTenant}>
                <div className="p-6 space-y-4">
                  {createError && (
                    <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded text-sm text-red-800 dark:text-red-200">
                      {createError}
                    </div>
                  )}

                  <div>
                    <label className="block text-sm font-medium text-white mb-2">
                      Organization Name
                    </label>
                    <input
                      type="text"
                      value={newTenant.name}
                      onChange={(e) => setNewTenant({ ...newTenant, name: e.target.value })}
                      placeholder="Acme Corp"
                      required
                      className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-white mb-2">
                      Owner Name
                    </label>
                    <input
                      type="text"
                      value={newTenant.owner_name}
                      onChange={(e) => setNewTenant({ ...newTenant, owner_name: e.target.value })}
                      placeholder="John Doe"
                      required
                      className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-white mb-2">
                      Owner Email
                    </label>
                    <input
                      type="email"
                      value={newTenant.owner_email}
                      onChange={(e) => setNewTenant({ ...newTenant, owner_email: e.target.value })}
                      placeholder="owner@example.com"
                      required
                      className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-white mb-2">
                      Owner Password
                    </label>
                    <input
                      type="password"
                      value={newTenant.owner_password}
                      onChange={(e) =>
                        setNewTenant({ ...newTenant, owner_password: e.target.value })
                      }
                      placeholder="Min 6 characters"
                      required
                      minLength={6}
                      className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-white mb-2">
                      Plan
                    </label>
                    <select
                      value={newTenant.plan}
                      onChange={(e) => setNewTenant({ ...newTenant, plan: e.target.value })}
                      className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface"
                    >
                      <option value="free">Free</option>
                      <option value="pro">Pro</option>
                      <option value="team">Team</option>
                      <option value="enterprise">Enterprise</option>
                    </select>
                  </div>
                </div>

                <div className="flex justify-end space-x-3 p-6 border-t border-tsushin-border">
                  <button
                    type="button"
                    onClick={() => setShowCreateModal(false)}
                    className="px-4 py-2 bg-tsushin-elevated text-white rounded-md"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={createLoading}
                    className="btn-primary px-4 py-2 rounded-md disabled:opacity-50"
                  >
                    {createLoading ? 'Creating...' : 'Create Tenant'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
