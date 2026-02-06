'use client'

/**
 * Plans Management Page (Global Admin Only)
 * Manages subscription plans for the platform
 */

import { useState, useEffect, useCallback } from 'react'
import { useRequireGlobalAdmin } from '@/contexts/AuthContext'
import { api, SubscriptionPlan, PlanCreate, PlanUpdate, PlanStats } from '@/lib/client'

// Available features for plans
const AVAILABLE_FEATURES = [
  { id: 'basic_support', label: 'Basic Support' },
  { id: 'priority_support', label: 'Priority Support' },
  { id: 'dedicated_support', label: 'Dedicated Support' },
  { id: 'playground', label: 'Playground' },
  { id: 'custom_tools', label: 'Sandboxed Tools' },
  { id: 'api_access', label: 'API Access' },
  { id: 'sso', label: 'Single Sign-On (SSO)' },
  { id: 'audit_logs', label: 'Audit Logs' },
  { id: 'advanced_analytics', label: 'Advanced Analytics' },
  { id: 'sla', label: 'SLA Guarantee' },
  { id: 'on_premise', label: 'On-Premise Deployment' },
  { id: 'custom_integrations', label: 'Custom Integrations' },
]

export default function PlansPage() {
  const { user, loading: authLoading } = useRequireGlobalAdmin()
  const [plans, setPlans] = useState<SubscriptionPlan[]>([])
  const [stats, setStats] = useState<PlanStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showInactive, setShowInactive] = useState(false)

  // Modal state
  const [showModal, setShowModal] = useState(false)
  const [editingPlan, setEditingPlan] = useState<SubscriptionPlan | null>(null)
  const [modalLoading, setModalLoading] = useState(false)
  const [modalError, setModalError] = useState<string | null>(null)

  // Form state
  const [formData, setFormData] = useState<PlanCreate>({
    name: '',
    display_name: '',
    description: '',
    price_monthly: 0,
    price_yearly: 0,
    max_users: 1,
    max_agents: 1,
    max_monthly_requests: 1000,
    max_knowledge_docs: 10,
    max_flows: 5,
    max_mcp_instances: 1,
    features: ['playground'],
    is_active: true,
    is_public: true,
    sort_order: 0,
  })

  // Fetch plans
  const fetchPlans = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await api.getAllPlans(showInactive)
      setPlans(response.plans)
    } catch (err) {
      console.error('Failed to fetch plans:', err)
      setError('Failed to load plans')
    } finally {
      setLoading(false)
    }
  }, [showInactive])

  // Fetch stats
  const fetchStats = useCallback(async () => {
    try {
      const response = await api.getPlanStats()
      setStats(response)
    } catch (err) {
      console.error('Failed to fetch plan stats:', err)
    }
  }, [])

  useEffect(() => {
    if (!authLoading && user) {
      fetchPlans()
      fetchStats()
    }
  }, [fetchPlans, fetchStats, authLoading, user])

  // Open create modal
  const openCreateModal = () => {
    setEditingPlan(null)
    setFormData({
      name: '',
      display_name: '',
      description: '',
      price_monthly: 0,
      price_yearly: 0,
      max_users: 1,
      max_agents: 1,
      max_monthly_requests: 1000,
      max_knowledge_docs: 10,
      max_flows: 5,
      max_mcp_instances: 1,
      features: ['playground'],
      is_active: true,
      is_public: true,
      sort_order: plans.length,
    })
    setModalError(null)
    setShowModal(true)
  }

  // Open edit modal
  const openEditModal = (plan: SubscriptionPlan) => {
    setEditingPlan(plan)
    setFormData({
      name: plan.name,
      display_name: plan.display_name,
      description: plan.description || '',
      price_monthly: plan.price_monthly,
      price_yearly: plan.price_yearly,
      max_users: plan.max_users,
      max_agents: plan.max_agents,
      max_monthly_requests: plan.max_monthly_requests,
      max_knowledge_docs: plan.max_knowledge_docs,
      max_flows: plan.max_flows,
      max_mcp_instances: plan.max_mcp_instances,
      features: plan.features,
      is_active: plan.is_active,
      is_public: plan.is_public,
      sort_order: plan.sort_order,
    })
    setModalError(null)
    setShowModal(true)
  }

  // Handle form submit
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setModalLoading(true)
    setModalError(null)

    try {
      if (editingPlan) {
        // Update existing plan
        const updateData: PlanUpdate = {
          display_name: formData.display_name,
          description: formData.description,
          price_monthly: formData.price_monthly,
          price_yearly: formData.price_yearly,
          max_users: formData.max_users,
          max_agents: formData.max_agents,
          max_monthly_requests: formData.max_monthly_requests,
          max_knowledge_docs: formData.max_knowledge_docs,
          max_flows: formData.max_flows,
          max_mcp_instances: formData.max_mcp_instances,
          features: formData.features,
          is_active: formData.is_active,
          is_public: formData.is_public,
          sort_order: formData.sort_order,
        }
        await api.updatePlan(editingPlan.id, updateData)
      } else {
        // Create new plan
        await api.createPlan(formData)
      }
      setShowModal(false)
      fetchPlans()
      fetchStats()
    } catch (err: any) {
      setModalError(err.message || 'Failed to save plan')
    } finally {
      setModalLoading(false)
    }
  }

  // Handle delete
  const handleDelete = async (plan: SubscriptionPlan) => {
    const message = plan.tenant_count > 0
      ? `This plan has ${plan.tenant_count} tenant(s) using it. Are you sure you want to deactivate it?`
      : 'Are you sure you want to deactivate this plan?'

    if (!confirm(message)) return

    try {
      await api.deletePlan(plan.id, plan.tenant_count > 0)
      fetchPlans()
      fetchStats()
    } catch (err: any) {
      alert(err.message || 'Failed to delete plan')
    }
  }

  // Format price
  const formatPrice = (cents: number) => {
    if (cents === 0) return 'Free'
    return `$${(cents / 100).toFixed(2)}`
  }

  // Format limit
  const formatLimit = (value: number) => {
    if (value === -1) return '∞'
    return value.toLocaleString()
  }

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-gray-600 dark:text-gray-400">Loading...</div>
      </div>
    )
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <div className="flex items-center space-x-3 mb-2">
              <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">
                Subscription Plans
              </h1>
              <span className="px-3 py-1 bg-purple-100 dark:bg-purple-900/30 text-purple-900 dark:text-purple-200 text-sm font-semibold rounded-full">
                Global Admin
              </span>
            </div>
            <p className="text-gray-600 dark:text-gray-400">
              Manage subscription plans and pricing
            </p>
          </div>

          <button
            onClick={openCreateModal}
            className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white font-medium rounded-md transition-colors"
          >
            + Create Plan
          </button>
        </div>

        {/* Stats */}
        {stats && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-6">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
              <div className="text-sm text-gray-600 dark:text-gray-400 mb-1">Total Plans</div>
              <div className="text-3xl font-bold text-gray-900 dark:text-gray-100">{stats.total_plans}</div>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
              <div className="text-sm text-gray-600 dark:text-gray-400 mb-1">Active Plans</div>
              <div className="text-3xl font-bold text-green-600 dark:text-green-400">{stats.active_plans}</div>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
              <div className="text-sm text-gray-600 dark:text-gray-400 mb-1">Public Plans</div>
              <div className="text-3xl font-bold text-blue-600 dark:text-blue-400">{stats.public_plans}</div>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
              <div className="text-sm text-gray-600 dark:text-gray-400 mb-1">Total Tenants</div>
              <div className="text-3xl font-bold text-purple-600 dark:text-purple-400">
                {Object.values(stats.tenants_per_plan).reduce((a, b) => a + b, 0)}
              </div>
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="mb-6 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
            <p className="text-sm text-red-800 dark:text-red-200">{error}</p>
            <button onClick={fetchPlans} className="mt-2 text-sm text-red-600 hover:underline">
              Retry
            </button>
          </div>
        )}

        {/* Filters */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4 mb-6">
          <label className="flex items-center space-x-2 cursor-pointer">
            <input
              type="checkbox"
              checked={showInactive}
              onChange={(e) => setShowInactive(e.target.checked)}
              className="rounded border-gray-300 dark:border-gray-600 text-purple-600 focus:ring-purple-500"
            />
            <span className="text-sm text-gray-700 dark:text-gray-300">Show inactive plans</span>
          </label>
        </div>

        {/* Plans Table */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
          {loading ? (
            <div className="p-8 text-center text-gray-600 dark:text-gray-400">
              Loading plans...
            </div>
          ) : plans.length === 0 ? (
            <div className="p-8 text-center text-gray-600 dark:text-gray-400">
              No plans found.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
                    <th className="text-left py-3 px-4 text-sm font-semibold text-gray-900 dark:text-gray-100">Plan</th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-gray-900 dark:text-gray-100">Price</th>
                    <th className="text-center py-3 px-4 text-sm font-semibold text-gray-900 dark:text-gray-100">Users</th>
                    <th className="text-center py-3 px-4 text-sm font-semibold text-gray-900 dark:text-gray-100">Agents</th>
                    <th className="text-center py-3 px-4 text-sm font-semibold text-gray-900 dark:text-gray-100">Requests/mo</th>
                    <th className="text-center py-3 px-4 text-sm font-semibold text-gray-900 dark:text-gray-100">Tenants</th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-gray-900 dark:text-gray-100">Status</th>
                    <th className="text-right py-3 px-4 text-sm font-semibold text-gray-900 dark:text-gray-100">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {plans.map((plan) => (
                    <tr
                      key={plan.id}
                      className={`border-b border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-900/50 ${!plan.is_active ? 'opacity-50' : ''
                        }`}
                    >
                      <td className="py-3 px-4">
                        <div>
                          <div className="font-medium text-gray-900 dark:text-gray-100">
                            {plan.display_name}
                          </div>
                          <div className="text-sm text-gray-600 dark:text-gray-400">
                            {plan.name}
                          </div>
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <div className="text-sm">
                          <div className="font-medium text-gray-900 dark:text-gray-100">
                            {formatPrice(plan.price_monthly)}/mo
                          </div>
                          {plan.price_yearly > 0 && (
                            <div className="text-gray-600 dark:text-gray-400">
                              {formatPrice(plan.price_yearly)}/yr
                            </div>
                          )}
                        </div>
                      </td>
                      <td className="py-3 px-4 text-center text-sm text-gray-700 dark:text-gray-300">
                        {formatLimit(plan.max_users)}
                      </td>
                      <td className="py-3 px-4 text-center text-sm text-gray-700 dark:text-gray-300">
                        {formatLimit(plan.max_agents)}
                      </td>
                      <td className="py-3 px-4 text-center text-sm text-gray-700 dark:text-gray-300">
                        {formatLimit(plan.max_monthly_requests)}
                      </td>
                      <td className="py-3 px-4 text-center">
                        <span className="px-2 py-1 bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-xs font-semibold rounded">
                          {plan.tenant_count}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex flex-col gap-1">
                          <span
                            className={`px-2 py-1 text-xs font-semibold rounded-full w-fit ${plan.is_active
                                ? 'bg-green-100 dark:bg-green-900/30 text-green-900 dark:text-green-200'
                                : 'bg-red-100 dark:bg-red-900/30 text-red-900 dark:text-red-200'
                              }`}
                          >
                            {plan.is_active ? 'ACTIVE' : 'INACTIVE'}
                          </span>
                          {plan.is_public && (
                            <span className="px-2 py-1 text-xs font-semibold rounded-full w-fit bg-blue-100 dark:bg-blue-900/30 text-blue-900 dark:text-blue-200">
                              PUBLIC
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-3 px-4 text-right">
                        <button
                          onClick={() => openEditModal(plan)}
                          className="text-sm text-purple-600 dark:text-purple-400 hover:underline mr-3"
                        >
                          Edit
                        </button>
                        {plan.is_active && (
                          <button
                            onClick={() => handleDelete(plan)}
                            className="text-sm text-red-600 dark:text-red-400 hover:underline"
                          >
                            Deactivate
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Create/Edit Modal */}
        {showModal && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4 overflow-y-auto">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-3xl w-full my-8">
              <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
                <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">
                  {editingPlan ? 'Edit Plan' : 'Create New Plan'}
                </h2>
                <button
                  onClick={() => setShowModal(false)}
                  className="p-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100"
                >
                  ✕
                </button>
              </div>

              <form onSubmit={handleSubmit}>
                <div className="p-6 space-y-6 max-h-[60vh] overflow-y-auto">
                  {modalError && (
                    <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded text-sm text-red-800 dark:text-red-200">
                      {modalError}
                    </div>
                  )}

                  {/* Basic Info */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                        Plan ID (lowercase, no spaces)
                      </label>
                      <input
                        type="text"
                        value={formData.name}
                        onChange={(e) => setFormData({ ...formData, name: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '') })}
                        placeholder="e.g. pro_plus"
                        required
                        disabled={!!editingPlan}
                        className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 disabled:opacity-50"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                        Display Name
                      </label>
                      <input
                        type="text"
                        value={formData.display_name}
                        onChange={(e) => setFormData({ ...formData, display_name: e.target.value })}
                        placeholder="e.g. Pro Plus"
                        required
                        className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                      Description
                    </label>
                    <textarea
                      value={formData.description}
                      onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                      placeholder="Plan description..."
                      rows={2}
                      className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
                    />
                  </div>

                  {/* Pricing */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                        Monthly Price (cents)
                      </label>
                      <input
                        type="number"
                        value={formData.price_monthly}
                        onChange={(e) => setFormData({ ...formData, price_monthly: parseInt(e.target.value) || 0 })}
                        min={0}
                        className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
                      />
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        {formatPrice(formData.price_monthly || 0)}/month
                      </p>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                        Yearly Price (cents)
                      </label>
                      <input
                        type="number"
                        value={formData.price_yearly}
                        onChange={(e) => setFormData({ ...formData, price_yearly: parseInt(e.target.value) || 0 })}
                        min={0}
                        className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
                      />
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        {formatPrice(formData.price_yearly || 0)}/year
                      </p>
                    </div>
                  </div>

                  {/* Limits */}
                  <div>
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
                      Plan Limits (-1 for unlimited)
                    </h3>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                      <div>
                        <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">Max Users</label>
                        <input
                          type="number"
                          value={formData.max_users}
                          onChange={(e) => setFormData({ ...formData, max_users: parseInt(e.target.value) || 0 })}
                          min={-1}
                          className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">Max Agents</label>
                        <input
                          type="number"
                          value={formData.max_agents}
                          onChange={(e) => setFormData({ ...formData, max_agents: parseInt(e.target.value) || 0 })}
                          min={-1}
                          className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">Requests/Month</label>
                        <input
                          type="number"
                          value={formData.max_monthly_requests}
                          onChange={(e) => setFormData({ ...formData, max_monthly_requests: parseInt(e.target.value) || 0 })}
                          min={-1}
                          className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">Knowledge Docs</label>
                        <input
                          type="number"
                          value={formData.max_knowledge_docs}
                          onChange={(e) => setFormData({ ...formData, max_knowledge_docs: parseInt(e.target.value) || 0 })}
                          min={-1}
                          className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">Flows</label>
                        <input
                          type="number"
                          value={formData.max_flows}
                          onChange={(e) => setFormData({ ...formData, max_flows: parseInt(e.target.value) || 0 })}
                          min={-1}
                          className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">MCP Instances</label>
                        <input
                          type="number"
                          value={formData.max_mcp_instances}
                          onChange={(e) => setFormData({ ...formData, max_mcp_instances: parseInt(e.target.value) || 0 })}
                          min={-1}
                          className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
                        />
                      </div>
                    </div>
                  </div>

                  {/* Features */}
                  <div>
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
                      Features
                    </h3>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                      {AVAILABLE_FEATURES.map((feature) => (
                        <label key={feature.id} className="flex items-center space-x-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={formData.features?.includes(feature.id) || false}
                            onChange={(e) => {
                              const features = formData.features || []
                              if (e.target.checked) {
                                setFormData({ ...formData, features: [...features, feature.id] })
                              } else {
                                setFormData({ ...formData, features: features.filter(f => f !== feature.id) })
                              }
                            }}
                            className="rounded border-gray-300 dark:border-gray-600 text-purple-600 focus:ring-purple-500"
                          />
                          <span className="text-sm text-gray-700 dark:text-gray-300">{feature.label}</span>
                        </label>
                      ))}
                    </div>
                  </div>

                  {/* Status */}
                  <div className="flex items-center space-x-6">
                    <label className="flex items-center space-x-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={formData.is_active}
                        onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                        className="rounded border-gray-300 dark:border-gray-600 text-purple-600 focus:ring-purple-500"
                      />
                      <span className="text-sm text-gray-700 dark:text-gray-300">Active</span>
                    </label>
                    <label className="flex items-center space-x-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={formData.is_public}
                        onChange={(e) => setFormData({ ...formData, is_public: e.target.checked })}
                        className="rounded border-gray-300 dark:border-gray-600 text-purple-600 focus:ring-purple-500"
                      />
                      <span className="text-sm text-gray-700 dark:text-gray-300">Public (show on pricing page)</span>
                    </label>
                    <div className="flex items-center space-x-2">
                      <label className="text-sm text-gray-700 dark:text-gray-300">Sort Order:</label>
                      <input
                        type="number"
                        value={formData.sort_order}
                        onChange={(e) => setFormData({ ...formData, sort_order: parseInt(e.target.value) || 0 })}
                        min={0}
                        className="w-20 px-2 py-1 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
                      />
                    </div>
                  </div>
                </div>

                <div className="flex justify-end space-x-3 p-6 border-t border-gray-200 dark:border-gray-700">
                  <button
                    type="button"
                    onClick={() => setShowModal(false)}
                    className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-gray-100 rounded-md"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={modalLoading}
                    className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-md disabled:opacity-50"
                  >
                    {modalLoading ? 'Saving...' : editingPlan ? 'Update Plan' : 'Create Plan'}
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
