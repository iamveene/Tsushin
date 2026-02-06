'use client'

/**
 * System Integrations Page
 * Global admin only - Manage platform-wide integrations
 * Phase 7.6.5 - Placeholder for global admin dashboard
 */

import { useRequireGlobalAdmin } from '@/contexts/AuthContext'

export default function SystemIntegrationsPage() {
  const { user, loading } = useRequireGlobalAdmin()

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-gray-600 dark:text-gray-400">Loading...</div>
      </div>
    )
  }

  if (!user) {
    return null // Redirect handled by hook
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
          System Integrations
        </h1>
        <p className="text-gray-600 dark:text-gray-400">
          Manage platform-wide integrations and services (Global Admin)
        </p>
      </div>

      <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-6">
        <div className="flex items-start">
          <div className="flex-shrink-0">
            <svg className="h-6 w-6 text-blue-600 dark:text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div className="ml-3">
            <h3 className="text-sm font-medium text-blue-800 dark:text-blue-300">
              Welcome, Global Admin!
            </h3>
            <div className="mt-2 text-sm text-blue-700 dark:text-blue-400">
              <p>You are logged in as: <strong>{user.email}</strong></p>
              <p className="mt-2">This page will contain:</p>
              <ul className="list-disc list-inside mt-2 space-y-1">
                <li>Platform-wide integration management</li>
                <li>System configuration</li>
                <li>Tenant overview and management</li>
                <li>Global analytics and monitoring</li>
              </ul>
              <p className="mt-4">
                <a href="/system/tenants" className="text-blue-600 dark:text-blue-400 hover:underline font-medium">
                  → Go to Tenant Management
                </a>
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* User Info Card */}
      <div className="mt-6 bg-white dark:bg-gray-800 shadow rounded-lg p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Your Account
        </h2>
        <dl className="grid grid-cols-1 gap-x-4 gap-y-4 sm:grid-cols-2">
          <div>
            <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Email</dt>
            <dd className="mt-1 text-sm text-gray-900 dark:text-white">{user.email}</dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Full Name</dt>
            <dd className="mt-1 text-sm text-gray-900 dark:text-white">{user.full_name}</dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Role</dt>
            <dd className="mt-1 text-sm text-gray-900 dark:text-white">
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300">
                Global Admin
              </span>
            </dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Tenant ID</dt>
            <dd className="mt-1 text-sm text-gray-900 dark:text-white font-mono text-xs">
              {user.tenant_id}
            </dd>
          </div>
        </dl>
      </div>
    </div>
  )
}
