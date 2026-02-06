'use client'

/**
 * Organization Settings Page
 * Shows organization details, plan, usage, and settings
 *
 * BUG-010 Fix: Now fetches real data from /api/tenants/current and /api/tenants/{id}/stats
 */

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { useAuth } from '@/contexts/AuthContext'
import { Input, Select } from '@/components/ui/form-input'
import UsageLimitCard from '@/components/rbac/UsageLimitCard'
import DangerZone from '@/components/rbac/DangerZone'
import { api, OrganizationData, OrganizationStats } from '@/lib/client'
import { SparklesIcon } from '@/components/ui/icons'

interface OrgState {
  id: string
  name: string
  slug: string
  plan: string
  maxUsers: number
  maxAgents: number
  maxRequests: number
  currentUsers: number
  currentAgents: number
  currentRequests: number
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

  // Listen for global refresh events
  useEffect(() => {
    const handleRefresh = () => {
      loadOrganizationData()
    }
    window.addEventListener('tsushin:refresh', handleRefresh)
    return () => window.removeEventListener('tsushin:refresh', handleRefresh)
  }, [])

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
        maxUsers: org.max_users,
        maxAgents: org.max_agents,
        maxRequests: org.max_monthly_requests,
        currentUsers: stats.users.current,
        currentAgents: stats.agents.current,
        currentRequests: stats.monthly_requests.current,
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
      await api.updateOrganization(orgData.id, { name: orgData.name })
      setSuccess(true)
      setTimeout(() => setSuccess(false), 3000)
    } catch (err) {
      console.error('Failed to save organization:', err)
      setError('Failed to save changes')
    } finally {
      setSaving(false)
    }
  }

  if (!hasPermission('users.read')) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-red-900 dark:text-red-100 mb-2">
            Access Denied
          </h3>
          <p className="text-sm text-red-800 dark:text-red-200">
            You don't have permission to view organization settings.
          </p>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-center h-64">
          <div className="text-lg text-gray-600 dark:text-gray-400">Loading organization...</div>
        </div>
      </div>
    )
  }

  if (error || !orgData) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-red-900 dark:text-red-100 mb-2">
            Error Loading Organization
          </h3>
          <p className="text-sm text-red-800 dark:text-red-200">
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
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">
            Organization Settings
          </h1>
          <p className="text-gray-600 dark:text-gray-400 mt-2">
            Manage your organization profile, plan, and settings
          </p>
        </div>

        {/* Back to Settings */}
        <Link
          href="/settings"
          className="inline-flex items-center gap-2 text-sm text-teal-400 hover:text-teal-300 mb-6 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Back to Settings
        </Link>

        {/* Success Message */}
        {success && (
          <div className="mb-6 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
            <p className="text-sm text-green-800 dark:text-green-200">
              ✓ Settings saved successfully!
            </p>
          </div>
        )}

        {/* Error Message */}
        {error && !loading && (
          <div className="mb-6 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
            <p className="text-sm text-red-800 dark:text-red-200">
              ✗ {error}
            </p>
          </div>
        )}

        <div className="space-y-8">
          {/* Basic Information */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-6">
              Basic Information
            </h2>

            <div className="space-y-4">
              <Input
                label="Organization Name"
                value={orgData.name}
                onChange={(e) => setOrgData({ ...orgData, name: e.target.value })}
                disabled={!canEdit}
                helperText="Display name for your organization"
              />

              <div>
                <label className="block text-sm font-medium mb-2 text-gray-900 dark:text-gray-100">
                  Organization URL
                </label>
                <div className="flex items-center space-x-2">
                  <Input
                    value={orgData.slug}
                    onChange={(e) => setOrgData({ ...orgData, slug: e.target.value })}
                    disabled={!canEdit}
                    className="flex-1"
                  />
                  <span className="text-sm text-gray-600 dark:text-gray-400 whitespace-nowrap">
                    .tsushin.com
                  </span>
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  hub.tsushin.com/{orgData.slug}
                </p>
              </div>

              <Input
                label="Organization ID (Read-only)"
                value={orgData.id}
                disabled
                helperText="Unique identifier for your organization"
              />
            </div>
          </div>

          {/* Plan & Limits */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-6">
              Plan & Limits
            </h2>

            <div className="mb-6 p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-lg font-semibold text-blue-900 dark:text-blue-100 inline-flex items-center gap-2">
                    <SparklesIcon size={18} /> {orgData.plan} Plan
                  </h3>
                  <p className="text-sm text-blue-800 dark:text-blue-200 mt-1">
                    $10/month
                  </p>
                </div>
                <div className="flex space-x-2">
                  <button className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-md transition-colors">
                    Upgrade Plan
                  </button>
                  <button className="px-4 py-2 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 text-gray-900 dark:text-gray-100 text-sm font-medium rounded-md transition-colors">
                    View Details
                  </button>
                </div>
              </div>

              <div className="text-sm text-blue-800 dark:text-blue-200 space-y-1">
                <div>• {orgData.maxUsers} team members</div>
                <div>• {orgData.maxAgents} agents</div>
                <div>• Unlimited integrations</div>
                <div>• {orgData.maxRequests.toLocaleString()} requests/month</div>
              </div>
            </div>

            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
              Usage This Month
            </h3>

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
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4">
                Save Changes
              </h2>
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                Save any changes made to your organization settings.
              </p>
              <button
                onClick={handleSave}
                disabled={saving}
                className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {saving ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          )}

          {/* Danger Zone */}
          {hasPermission('org.settings.write') && <DangerZone />}
        </div>
      </div>
    </div>
  )
}
