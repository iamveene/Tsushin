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
        <div className="text-gray-600 dark:text-gray-400">Loading...</div>
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
              <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">
                Tenant Management
              </h1>
              <span className="px-3 py-1 bg-purple-100 dark:bg-purple-900/30 text-purple-900 dark:text-purple-200 text-sm font-semibold rounded-full inline-flex items-center gap-1">
                <GlobeIcon size={14} /> Global Admin
              </span>
            </div>
            <p className="text-gray-600 dark:text-gray-400">
              Manage all organizations on the platform
            </p>
          </div>

          <button
            onClick={() => setShowCreateModal(true)}
            className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white font-medium rounded-md transition-colors"
          >
            + Create Tenant
          </button>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-6">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
            <div className="text-sm text-gray-600 dark:text-gray-400 mb-1">Total Tenants</div>
            <div className="text-3xl font-bold text-gray-900 dark:text-gray-100">{stats.total}</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
            <div className="text-sm text-gray-600 dark:text-gray-400 mb-1">Active</div>
            <div className="text-3xl font-bold text-green-600 dark:text-green-400">
              {stats.active}
            </div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
            <div className="text-sm text-gray-600 dark:text-gray-400 mb-1">Trial</div>
            <div className="text-3xl font-bold text-yellow-600 dark:text-yellow-400">
              {stats.trial}
            </div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
            <div className="text-sm text-gray-600 dark:text-gray-400 mb-1">Suspended</div>
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
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 mb-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                Search Tenants
              </label>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search by name or slug..."
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 focus:ring-2 focus:ring-purple-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                Filter by Status
              </label>
              <select
                value={filterStatus}
                onChange={(e) => {
                  setFilterStatus(e.target.value)
                  setPage(1)
                }}
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
              >
                <option value="all">All Status</option>
                <option value="active">Active</option>
                <option value="trial">Trial</option>
                <option value="suspended">Suspended</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                Filter by Plan
              </label>
              <select
                value={filterPlan}
                onChange={(e) => {
                  setFilterPlan(e.target.value)
                  setPage(1)
                }}
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
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
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
          {loading ? (
            <div className="p-8 text-center text-gray-600 dark:text-gray-400">
              Loading tenants...
            </div>
          ) : tenants.length === 0 ? (
            <div className="p-8 text-center text-gray-600 dark:text-gray-400">
              No tenants found matching your filters.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
                    <th className="text-left py-3 px-4 text-sm font-semibold text-gray-900 dark:text-gray-100">
                      Organization
                    </th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-gray-900 dark:text-gray-100">
                      Plan
                    </th>
                    <th className="text-center py-3 px-4 text-sm font-semibold text-gray-900 dark:text-gray-100">
                      Users
                    </th>
                    <th className="text-center py-3 px-4 text-sm font-semibold text-gray-900 dark:text-gray-100">
                      Agents
                    </th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-gray-900 dark:text-gray-100">
                      Status
                    </th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-gray-900 dark:text-gray-100">
                      Created
                    </th>
                    <th className="text-right py-3 px-4 text-sm font-semibold text-gray-900 dark:text-gray-100">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {tenants.map((tenant) => (
                    <tr
                      key={tenant.id}
                      className="border-b border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-900/50"
                    >
                      <td className="py-3 px-4">
                        <div>
                          <div className="font-medium text-gray-900 dark:text-gray-100">
                            {tenant.name}
                          </div>
                          <div className="text-sm text-gray-600 dark:text-gray-400">
                            {tenant.slug}
                          </div>
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <span className="px-2 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-900 dark:text-blue-200 text-xs font-semibold rounded">
                          {tenant.plan}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-center text-sm text-gray-700 dark:text-gray-300">
                        {tenant.user_count} / {tenant.max_users}
                      </td>
                      <td className="py-3 px-4 text-center text-sm text-gray-700 dark:text-gray-300">
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
                      <td className="py-3 px-4 text-sm text-gray-700 dark:text-gray-300">
                        {tenant.created_at
                          ? new Date(tenant.created_at).toLocaleDateString()
                          : 'N/A'}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <button className="text-sm text-purple-600 dark:text-purple-400 hover:underline mr-3">
                          View
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
            <div className="flex items-center justify-between p-4 border-t border-gray-200 dark:border-gray-700">
              <div className="text-sm text-gray-600 dark:text-gray-400">
                Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, total)} of{' '}
                {total} tenants
              </div>
              <div className="flex space-x-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="px-3 py-1 bg-gray-200 dark:bg-gray-700 rounded disabled:opacity-50"
                >
                  Previous
                </button>
                <button
                  onClick={() => setPage((p) => p + 1)}
                  disabled={page * pageSize >= total}
                  className="px-3 py-1 bg-gray-200 dark:bg-gray-700 rounded disabled:opacity-50"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Create Tenant Modal */}
        {showCreateModal && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-2xl w-full">
              <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
                <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">
                  Create New Tenant
                </h2>
                <button
                  onClick={() => setShowCreateModal(false)}
                  className="p-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100"
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
                    <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                      Organization Name
                    </label>
                    <input
                      type="text"
                      value={newTenant.name}
                      onChange={(e) => setNewTenant({ ...newTenant, name: e.target.value })}
                      placeholder="Acme Corp"
                      required
                      className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                      Owner Name
                    </label>
                    <input
                      type="text"
                      value={newTenant.owner_name}
                      onChange={(e) => setNewTenant({ ...newTenant, owner_name: e.target.value })}
                      placeholder="John Doe"
                      required
                      className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                      Owner Email
                    </label>
                    <input
                      type="email"
                      value={newTenant.owner_email}
                      onChange={(e) => setNewTenant({ ...newTenant, owner_email: e.target.value })}
                      placeholder="owner@example.com"
                      required
                      className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                      Owner Password
                    </label>
                    <input
                      type="password"
                      value={newTenant.owner_password}
                      onChange={(e) =>
                        setNewTenant({ ...newTenant, owner_password: e.target.value })
                      }
                      placeholder="Min 8 characters"
                      required
                      minLength={8}
                      className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                      Plan
                    </label>
                    <select
                      value={newTenant.plan}
                      onChange={(e) => setNewTenant({ ...newTenant, plan: e.target.value })}
                      className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
                    >
                      <option value="free">Free</option>
                      <option value="pro">Pro</option>
                      <option value="team">Team</option>
                      <option value="enterprise">Enterprise</option>
                    </select>
                  </div>
                </div>

                <div className="flex justify-end space-x-3 p-6 border-t border-gray-200 dark:border-gray-700">
                  <button
                    type="button"
                    onClick={() => setShowCreateModal(false)}
                    className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-gray-100 rounded-md"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={createLoading}
                    className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-md disabled:opacity-50"
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
