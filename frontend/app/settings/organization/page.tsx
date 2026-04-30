'use client'

/**
 * Organization Settings Page
 * Shows organization details, plan, usage, and settings
 *
 * BUG-010 Fix: Now fetches real data from /api/tenants/current and /api/tenants/{id}/stats
 */

import { useState, useEffect } from 'react'
import { useGlobalRefresh } from '@/hooks/useGlobalRefresh'
import Link from 'next/link'
import { useAuth } from '@/contexts/AuthContext'
import { Input } from '@/components/ui/form-input'
import UsageLimitCard from '@/components/rbac/UsageLimitCard'
import DangerZone from '@/components/rbac/DangerZone'
import { api, OrganizationData, OrganizationStats } from '@/lib/client'
import { SparklesIcon } from '@/components/ui/icons'

interface OrgState {
  id: string
  name: string
  slug: string
  plan: string
  planDisplayName: string | null
  planPriceMonthly: number | null
  maxUsers: number
  maxAgents: number
  maxRequests: number
  currentUsers: number
  currentAgents: number
  currentRequests: number
  caseMemoryEnabled: boolean
  caseMemoryRecapEnabled: boolean
}

export default function OrganizationSettingsPage() {
  const { user, hasPermission } = useAuth()
  const [orgData, setOrgData] = useState<OrgState | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const canEdit = hasPermission('org.settings.write')

  // BUG-010 Fix: Load real organization data on mount
  useEffect(() => {
    loadOrganizationData()
  }, [])

  useGlobalRefresh(() => loadOrganizationData())

  const loadOrganizationData = async () => {
    setLoading(true)
    setError(null)
    try {
      const org = await api.getCurrentOrganization()
      const stats = await api.getOrganizationStats(org.id)

      setOrgData({
        id: org.id,
        name: org.name,
        slug: org.slug,
        plan: org.plan,
        planDisplayName: (org as any).plan_display_name || null,
        planPriceMonthly: (org as any).plan_price_monthly ?? null,
        maxUsers: org.max_users,
        maxAgents: org.max_agents,
        maxRequests: org.max_monthly_requests,
        currentUsers: stats.users.current,
        currentAgents: stats.agents.current,
        currentRequests: stats.monthly_requests.current,
        caseMemoryEnabled: org.case_memory_enabled !== false,
        caseMemoryRecapEnabled: org.case_memory_recap_enabled !== false,
      })
    } catch (err) {
      console.error('Failed to load organization:', err)
      setError('Failed to load organization data')
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    if (!orgData) return

    setSaving(true)
    setSuccess(false)
    setError(null)

    try {
      await api.updateOrganization(orgData.id, { name: orgData.name, slug: orgData.slug })
      setSuccess(true)
      setTimeout(() => setSuccess(false), 3000)
    } catch (err: any) {
      console.error('Failed to save organization:', err)
      const detail = err?.response?.data?.detail || err?.message || 'Failed to save changes'
      setError(typeof detail === 'string' ? detail : 'Failed to save changes')
    } finally {
      setSaving(false)
    }
  }

  // v0.7.x — flip a single case-memory toggle. Each call PUTs only the
  // changed field so the user gets an immediate save on click rather
  // than a separate "Save" button for this section.
  const handleCaseMemoryToggle = async (
    field: 'case_memory_enabled' | 'case_memory_recap_enabled',
    nextValue: boolean,
  ) => {
    if (!orgData || !canEdit) return
    const previous = orgData
    // Optimistic UI update.
    setOrgData({
      ...orgData,
      caseMemoryEnabled: field === 'case_memory_enabled' ? nextValue : orgData.caseMemoryEnabled,
      caseMemoryRecapEnabled:
        field === 'case_memory_recap_enabled' ? nextValue : orgData.caseMemoryRecapEnabled,
    })
    setError(null)
    setSuccess(false)
    try {
      const result = await api.updateOrganizationCaseMemoryConfig(orgData.id, {
        [field]: nextValue,
      })
      setOrgData((current) =>
        current
          ? {
              ...current,
              caseMemoryEnabled: result.case_memory_enabled,
              caseMemoryRecapEnabled: result.case_memory_recap_enabled,
            }
          : current,
      )
      setSuccess(true)
      setTimeout(() => setSuccess(false), 3000)
    } catch (err: any) {
      console.error('Failed to save case memory config:', err)
      // Roll back optimistic update.
      setOrgData(previous)
      const detail = err?.response?.data?.detail || err?.message || 'Failed to save case memory setting'
      setError(typeof detail === 'string' ? detail : 'Failed to save case memory setting')
    }
  }

  const formatPrice = (cents: number | null): string => {
    if (cents === null || cents === undefined) return 'Custom'
    if (cents === 0) return 'Free'
    return `$${(cents / 100).toFixed(cents % 100 === 0 ? 0 : 2)}/month`
  }

  if (!hasPermission('users.read')) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="bg-red-900/20 border border-red-800 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-red-100 mb-2">Access Denied</h3>
          <p className="text-sm text-red-200">
            You don&apos;t have permission to view organization settings.
          </p>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-center h-64">
          <div className="text-lg text-tsushin-slate">Loading organization...</div>
        </div>
      </div>
    )
  }

  if (error || !orgData) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="bg-red-900/20 border border-red-800 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-red-100 mb-2">Error Loading Organization</h3>
          <p className="text-sm text-red-200">
            {error || 'Organization data not available'}
          </p>
          <button
            onClick={loadOrganizationData}
            className="mt-4 px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-sm font-medium rounded-md transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-4xl mx-auto">
        {/* Back link */}
        <Link
          href="/settings"
          className="inline-flex items-center gap-2 text-sm text-teal-400 hover:text-teal-300 mb-6 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Back to Settings
        </Link>

        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-display font-bold text-white">Organization Settings</h1>
          <p className="text-tsushin-slate mt-2">
            Manage your organization profile, plan, and settings
          </p>
        </div>

        {/* Status Messages */}
        {success && (
          <div className="mb-6 p-4 bg-green-500/10 border border-green-500/30 rounded-lg text-green-400">
            Settings saved successfully
          </div>
        )}
        {error && !loading && (
          <div className="mb-6 p-4 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400">
            {error}
          </div>
        )}

        <div className="space-y-8">
          {/* Basic Information */}
          <div className="glass-card rounded-xl p-6">
            <h2 className="text-xl font-semibold text-white mb-6">Basic Information</h2>

            <div className="space-y-4">
              <Input
                label="Organization Name"
                value={orgData.name}
                onChange={(e) => setOrgData({ ...orgData, name: e.target.value })}
                disabled={!canEdit}
                helperText="Display name for your organization"
              />

              <Input
                label="Organization Slug"
                value={orgData.slug}
                onChange={(e) => setOrgData({ ...orgData, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '') })}
                disabled={!canEdit}
                helperText="URL-safe identifier for your organization (lowercase, alphanumeric, hyphens)"
              />

              <Input
                label="Organization ID"
                value={orgData.id}
                disabled
                helperText="Unique system identifier (read-only)"
              />

              <div>
                <label className="block text-sm font-medium mb-2 text-white/70">Status</label>
                <span className={`inline-flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg ${
                  orgData.plan === 'free'
                    ? 'bg-white/5 text-white/50'
                    : 'bg-teal-500/10 text-teal-400'
                }`}>
                  <SparklesIcon size={14} />
                  {orgData.planDisplayName || orgData.plan.charAt(0).toUpperCase() + orgData.plan.slice(1)} Plan
                </span>
              </div>
            </div>
          </div>

          {/* Plan & Limits */}
          <div className="glass-card rounded-xl p-6">
            <h2 className="text-xl font-semibold text-white mb-6">Plan & Limits</h2>

            <div className="mb-6 p-4 bg-teal-500/5 border border-teal-500/20 rounded-lg">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-lg font-semibold text-white inline-flex items-center gap-2">
                    <SparklesIcon size={18} />
                    {orgData.planDisplayName || orgData.plan.charAt(0).toUpperCase() + orgData.plan.slice(1)} Plan
                  </h3>
                  <p className="text-sm text-tsushin-slate mt-1">
                    {formatPrice(orgData.planPriceMonthly)}
                  </p>
                </div>
              </div>

              <div className="text-sm text-tsushin-slate space-y-1">
                <div>{orgData.maxUsers === -1 ? 'Unlimited' : orgData.maxUsers} team members</div>
                <div>{orgData.maxAgents === -1 ? 'Unlimited' : orgData.maxAgents} agents</div>
                <div>{orgData.maxRequests === -1 ? 'Unlimited' : orgData.maxRequests.toLocaleString()} requests/month</div>
              </div>
            </div>

            <h3 className="text-lg font-semibold text-white mb-4">Usage This Month</h3>

            <div className="space-y-6">
              <UsageLimitCard
                title="Team Members"
                current={orgData.currentUsers}
                limit={orgData.maxUsers}
              />
              <UsageLimitCard
                title="Agents"
                current={orgData.currentAgents}
                limit={orgData.maxAgents}
              />
              <UsageLimitCard
                title="Requests"
                current={orgData.currentRequests}
                limit={orgData.maxRequests}
              />
            </div>
          </div>

          {/* Save Button */}
          {canEdit && (
            <div className="glass-card rounded-xl p-6">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-white">Save Changes</h2>
                  <p className="text-sm text-tsushin-slate">
                    Save any changes made to your organization settings.
                  </p>
                </div>
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="px-6 py-2 bg-teal-600 hover:bg-teal-700 text-white font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {saving ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </div>
          )}

          {/* Case Memory (v0.7.x) — per-tenant gates for the trigger
              case-memory subsystem. Both flags default TRUE per tenant
              and are managed entirely from this UI (no env var). */}
          <div className="glass-card rounded-xl p-6">
            <h2 className="text-xl font-semibold text-white mb-2">Case Memory</h2>
            <p className="text-sm text-tsushin-slate mb-6">
              Control how trigger-driven runs accumulate and re-use organizational memory.
            </p>

            <div className="space-y-6">
              {/* Indexer toggle */}
              <div className="flex items-start justify-between gap-6">
                <div className="flex-1 min-w-0">
                  <label
                    htmlFor="case-memory-enabled"
                    className="block text-sm font-medium text-white mb-1"
                  >
                    Enable trigger case memory
                  </label>
                  <p className="text-xs text-tsushin-slate leading-relaxed">
                    When enabled, terminal trigger-driven runs index a compact case row plus
                    problem/action/outcome vectors for the agent&apos;s resolved vector store.
                    Past cases become searchable via the{' '}
                    <code className="text-teal-400">find_similar_past_cases</code> skill.
                  </p>
                </div>
                <button
                  id="case-memory-enabled"
                  type="button"
                  role="switch"
                  aria-checked={orgData.caseMemoryEnabled}
                  disabled={!canEdit}
                  onClick={() =>
                    handleCaseMemoryToggle('case_memory_enabled', !orgData.caseMemoryEnabled)
                  }
                  className={`relative inline-flex h-6 w-11 flex-shrink-0 items-center rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                    orgData.caseMemoryEnabled ? 'bg-teal-500' : 'bg-white/10'
                  }`}
                >
                  <span className="sr-only">Toggle case memory</span>
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition ${
                      orgData.caseMemoryEnabled ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>

              {/* Recap injection toggle — depends on the indexer flag. */}
              <div
                className={`flex items-start justify-between gap-6 ${
                  orgData.caseMemoryEnabled ? '' : 'opacity-50'
                }`}
              >
                <div className="flex-1 min-w-0">
                  <label
                    htmlFor="case-memory-recap-enabled"
                    className="block text-sm font-medium text-white mb-1"
                  >
                    Inject memory recap into agent context at dispatch
                  </label>
                  <p className="text-xs text-tsushin-slate leading-relaxed">
                    When enabled, the trigger dispatcher pre-builds a memory recap from past
                    similar cases and prepends it to the agent&apos;s first-turn context.
                    Disabling this stops recap injection cluster-wide for this tenant without
                    touching individual trigger configs.
                  </p>
                </div>
                <button
                  id="case-memory-recap-enabled"
                  type="button"
                  role="switch"
                  aria-checked={orgData.caseMemoryRecapEnabled}
                  disabled={!canEdit || !orgData.caseMemoryEnabled}
                  onClick={() =>
                    handleCaseMemoryToggle(
                      'case_memory_recap_enabled',
                      !orgData.caseMemoryRecapEnabled,
                    )
                  }
                  className={`relative inline-flex h-6 w-11 flex-shrink-0 items-center rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                    orgData.caseMemoryRecapEnabled ? 'bg-teal-500' : 'bg-white/10'
                  }`}
                >
                  <span className="sr-only">Toggle memory recap injection</span>
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition ${
                      orgData.caseMemoryRecapEnabled ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>
            </div>
          </div>

          {/* Danger Zone */}
          {hasPermission('org.settings.write') && <DangerZone />}
        </div>
      </div>
    </div>
  )
}
