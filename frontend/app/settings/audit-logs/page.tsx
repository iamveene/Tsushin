'use client'

/**
 * Audit Logs Page
 * Shows activity history for the organization
 */

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { useAuth } from '@/contexts/AuthContext'
import { api } from '@/lib/client'
import AuditLogEntry from '@/components/rbac/AuditLogEntry'

interface AuditLog {
  id: number
  action: string
  user: string
  resource?: string
  timestamp: string
  ipAddress?: string
  details?: string
}

export default function AuditLogsPage() {
  const { hasPermission } = useAuth()
  const [logs, setLogs] = useState<AuditLog[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filterAction, setFilterAction] = useState('all')
  const [filterUser, setFilterUser] = useState('')
  const [offset, setOffset] = useState(0)
  const PAGE_SIZE = 50

  const fetchLogs = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await api.getAuditLogs({
        limit: PAGE_SIZE,
        offset,
        action: filterAction !== 'all' ? filterAction : undefined,
      })
      if (offset === 0) {
        setLogs(data.logs)
      } else {
        setLogs((prev) => [...prev, ...data.logs])
      }
      setTotal(data.total)
    } catch (err) {
      console.error('Failed to fetch audit logs:', err)
      setError('Failed to load audit logs')
    } finally {
      setLoading(false)
    }
  }, [offset, filterAction])

  useEffect(() => {
    if (hasPermission('users.read')) {
      setOffset(0)
    }
  }, [filterAction, hasPermission])

  useEffect(() => {
    if (hasPermission('users.read')) {
      fetchLogs()
    }
  }, [fetchLogs, hasPermission])

  if (!hasPermission('users.read')) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-red-900 dark:text-red-100 mb-2">
            Access Denied
          </h3>
          <p className="text-sm text-red-800 dark:text-red-200">
            You don&apos;t have permission to view audit logs.
          </p>
        </div>
      </div>
    )
  }

  // Client-side filter by user name
  const filteredLogs = logs.filter((log) => {
    return !filterUser || log.user.toLowerCase().includes(filterUser.toLowerCase())
  })

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white">Audit Logs</h1>
          <p className="text-tsushin-slate mt-2">
            Track all activities in your organization
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

        {/* Filters */}
        <div className="bg-tsushin-surface rounded-lg shadow-md p-6 mb-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-white mb-2">
                Filter by Action
              </label>
              <select
                value={filterAction}
                onChange={(e) => setFilterAction(e.target.value)}
                className="w-full px-3 py-2 border border-white/10 rounded-md text-white bg-tsushin-surface"
              >
                <option value="all">All Actions</option>
                <option value="user">User Actions</option>
                <option value="tenant">Tenant Actions</option>
                <option value="integration">Integration Actions</option>
                <option value="plan">Plan Actions</option>
                <option value="sso">SSO Actions</option>
                <option value="system">System Actions</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-white mb-2">
                Filter by User
              </label>
              <input
                type="text"
                value={filterUser}
                onChange={(e) => setFilterUser(e.target.value)}
                placeholder="Search by user name..."
                className="w-full px-3 py-2 border border-white/10 rounded-md text-white bg-tsushin-surface focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          <div className="mt-4 flex items-center justify-between">
            <span className="text-sm text-tsushin-slate">
              Showing {filteredLogs.length} of {total} events
            </span>
          </div>
        </div>

        {/* Error State */}
        {error && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 mb-6">
            <p className="text-sm text-red-800 dark:text-red-200">{error}</p>
          </div>
        )}

        {/* Loading State */}
        {loading && logs.length === 0 && (
          <div className="bg-tsushin-surface rounded-lg shadow-md p-8 text-center">
            <p className="text-tsushin-slate">Loading audit logs...</p>
          </div>
        )}

        {/* Audit Log Entries */}
        {!loading && logs.length === 0 && !error && (
          <div className="bg-tsushin-surface rounded-lg shadow-md p-8 text-center">
            <p className="text-tsushin-slate">No audit logs found.</p>
          </div>
        )}

        {filteredLogs.length > 0 && (
          <div className="bg-tsushin-surface rounded-lg shadow-md">
            <div className="divide-y divide-white/10">
              {filteredLogs.map((log) => (
                <AuditLogEntry
                  key={log.id}
                  action={log.action}
                  user={log.user}
                  resource={log.resource}
                  timestamp={log.timestamp}
                  ipAddress={log.ipAddress}
                  details={log.details}
                />
              ))}
            </div>
          </div>
        )}

        {/* Load More */}
        {logs.length < total && (
          <div className="mt-6 text-center">
            <button
              onClick={() => setOffset((prev) => prev + PAGE_SIZE)}
              disabled={loading}
              className="px-6 py-2 bg-white/10 hover:bg-white/15 text-white font-medium rounded-md transition-colors disabled:opacity-50"
            >
              {loading ? 'Loading...' : 'Load More'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
