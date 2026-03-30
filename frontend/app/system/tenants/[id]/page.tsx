'use client'

/**
 * Tenant Detail Page (Global Admin Only)
 * Shows detailed information about a specific tenant
 */

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useRequireGlobalAdmin } from '@/contexts/AuthContext'
import { api, TenantInfo, TenantStats } from '@/lib/client'

export default function TenantDetailPage() {
  const { user, loading: authLoading } = useRequireGlobalAdmin()
  const router = useRouter()
  const params = useParams()
  const tenantId = params?.id as string

  const [tenant, setTenant] = useState<TenantInfo | null>(null)
  const [stats, setStats] = useState<TenantStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!authLoading && user && tenantId) {
      const fetchData = async () => {
        setLoading(true)
        setError(null)
        try {
          const [tenantData, statsData] = await Promise.all([
            api.getTenant(tenantId),
            api.getTenantStats(tenantId),
          ])
          setTenant(tenantData)
          setStats(statsData)
        } catch (err) {
          console.error('Failed to fetch tenant details:', err)
          setError('Failed to load tenant details')
        } finally {
          setLoading(false)
        }
      }
      fetchData()
    }
  }, [authLoading, user, tenantId])

  if (authLoading || loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-tsushin-slate">Loading...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="text-red-400">{error}</div>
        <button onClick={() => router.back()} className="mt-4 text-sm text-teal-400 hover:underline">
          ← Back to Tenants
        </button>
      </div>
    )
  }

  if (!tenant) return null

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <button onClick={() => router.push('/system/tenants')} className="text-sm text-teal-400 hover:underline mb-6 block">
        ← Back to Tenants
      </button>

      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-tsushin-text">{tenant.name}</h1>
        <p className="text-tsushin-slate text-sm mt-1">ID: {tenant.id} · Slug: {tenant.slug}</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <div className="bg-tsushin-elevated rounded-lg p-4 border border-tsushin-border">
          <h2 className="text-sm font-medium text-tsushin-slate mb-3">Overview</h2>
          <dl className="space-y-2">
            <div className="flex justify-between text-sm">
              <dt className="text-tsushin-slate">Status</dt>
              <dd>
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                  tenant.status === 'active' ? 'bg-tsushin-success/20 text-tsushin-success' :
                  tenant.status === 'suspended' ? 'bg-tsushin-vermilion/20 text-tsushin-vermilion' :
                  'bg-tsushin-warning/20 text-tsushin-warning'
                }`}>
                  {tenant.status.toUpperCase()}
                </span>
              </dd>
            </div>
            <div className="flex justify-between text-sm">
              <dt className="text-tsushin-slate">Plan</dt>
              <dd className="text-tsushin-text capitalize">{tenant.plan}</dd>
            </div>
            <div className="flex justify-between text-sm">
              <dt className="text-tsushin-slate">Created</dt>
              <dd className="text-tsushin-text">
                {tenant.created_at ? new Date(tenant.created_at).toLocaleDateString() : 'N/A'}
              </dd>
            </div>
          </dl>
        </div>

        <div className="bg-tsushin-elevated rounded-lg p-4 border border-tsushin-border">
          <h2 className="text-sm font-medium text-tsushin-slate mb-3">Usage</h2>
          <dl className="space-y-2">
            <div className="flex justify-between text-sm">
              <dt className="text-tsushin-slate">Users</dt>
              <dd className="text-tsushin-text">{tenant.user_count} / {tenant.max_users}</dd>
            </div>
            <div className="flex justify-between text-sm">
              <dt className="text-tsushin-slate">Agents</dt>
              <dd className="text-tsushin-text">{tenant.agent_count} / {tenant.max_agents}</dd>
            </div>
            {stats && (
              <div className="flex justify-between text-sm">
                <dt className="text-tsushin-slate">Monthly Requests</dt>
                <dd className="text-tsushin-text">
                  {stats.monthly_requests.current.toLocaleString()} / {stats.monthly_requests.limit.toLocaleString()}
                </dd>
              </div>
            )}
          </dl>
        </div>
      </div>

      {stats && (
        <div className="bg-tsushin-elevated rounded-lg p-4 border border-tsushin-border">
          <h2 className="text-sm font-medium text-tsushin-slate mb-3">Resource Utilization</h2>
          <div className="space-y-3">
            {(['users', 'agents', 'monthly_requests'] as const).map((key) => (
              <div key={key}>
                <div className="flex justify-between text-xs text-tsushin-slate mb-1">
                  <span className="capitalize">{key.replace('_', ' ')}</span>
                  <span>{stats[key].percentage.toFixed(1)}%</span>
                </div>
                <div className="h-1.5 bg-tsushin-surface rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${
                      stats[key].percentage > 90 ? 'bg-tsushin-vermilion' :
                      stats[key].percentage > 75 ? 'bg-tsushin-warning' :
                      'bg-teal-500'
                    }`}
                    style={{ width: `${Math.min(stats[key].percentage, 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
