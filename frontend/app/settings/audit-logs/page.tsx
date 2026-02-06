'use client'

/**
 * Audit Logs Page
 * Shows activity history for the organization
 */

import { useState } from 'react'
import Link from 'next/link'
import { useAuth } from '@/contexts/AuthContext'
import AuditLogEntry from '@/components/rbac/AuditLogEntry'

// Mock audit log data
const MOCK_LOGS = [
  {
    id: 1,
    action: 'user.invited',
    user: 'Admin',
    resource: 'newuser@example.com',
    timestamp: '2 hours ago',
    ipAddress: '192.168.1.100',
    details: 'invited newuser@example.com as Member',
  },
  {
    id: 2,
    action: 'settings.updated',
    user: 'Alice',
    resource: 'Organization Settings',
    timestamp: '5 hours ago',
    ipAddress: '192.168.1.101',
    details: 'updated organization timezone to UTC',
  },
  {
    id: 3,
    action: 'agent.created',
    user: 'John Smith',
    resource: 'Agent: Marketing Bot',
    timestamp: '1 day ago',
    ipAddress: '192.168.1.102',
    details: 'created new agent "Marketing Bot"',
  },
  {
    id: 4,
    action: 'user.role_changed',
    user: 'Admin',
    resource: 'john@example.com',
    timestamp: '2 days ago',
    ipAddress: '192.168.1.100',
    details: 'changed role from Read-Only to Member',
  },
  {
    id: 5,
    action: 'billing.updated',
    user: 'Admin',
    resource: 'Billing',
    timestamp: '3 days ago',
    ipAddress: '192.168.1.100',
    details: 'upgraded plan from Free to Pro',
  },
  {
    id: 6,
    action: 'agent.deleted',
    user: 'Alice',
    resource: 'Agent: Old Bot',
    timestamp: '4 days ago',
    ipAddress: '192.168.1.101',
    details: 'deleted agent "Old Bot"',
  },
  {
    id: 7,
    action: 'login',
    user: 'Maria Santos',
    timestamp: '5 days ago',
    ipAddress: '192.168.1.103',
    details: 'logged in',
  },
  {
    id: 8,
    action: 'user.removed',
    user: 'Admin',
    resource: 'olduser@example.com',
    timestamp: '1 week ago',
    ipAddress: '192.168.1.100',
    details: 'removed olduser@example.com from organization',
  },
]

export default function AuditLogsPage() {
  const { hasPermission } = useAuth()
  const [logs, setLogs] = useState(MOCK_LOGS)
  const [filterAction, setFilterAction] = useState('all')
  const [filterUser, setFilterUser] = useState('')

  if (!hasPermission('users.read')) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-red-900 dark:text-red-100 mb-2">
            Access Denied
          </h3>
          <p className="text-sm text-red-800 dark:text-red-200">
            You don't have permission to view audit logs.
          </p>
        </div>
      </div>
    )
  }

  // Filter logs
  const filteredLogs = logs.filter((log) => {
    const matchesAction = filterAction === 'all' || log.action.startsWith(filterAction)
    const matchesUser =
      !filterUser || log.user.toLowerCase().includes(filterUser.toLowerCase())
    return matchesAction && matchesUser
  })

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">Audit Logs</h1>
          <p className="text-gray-600 dark:text-gray-400 mt-2">
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
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 mb-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                Filter by Action
              </label>
              <select
                value={filterAction}
                onChange={(e) => setFilterAction(e.target.value)}
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
              >
                <option value="all">All Actions</option>
                <option value="user">User Actions</option>
                <option value="agent">Agent Actions</option>
                <option value="settings">Settings Changes</option>
                <option value="billing">Billing Actions</option>
                <option value="login">Login/Logout</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                Filter by User
              </label>
              <input
                type="text"
                value={filterUser}
                onChange={(e) => setFilterUser(e.target.value)}
                placeholder="Search by user name..."
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          <div className="mt-4 flex items-center justify-between">
            <span className="text-sm text-gray-600 dark:text-gray-400">
              Showing {filteredLogs.length} of {logs.length} events
            </span>
            <button className="text-sm text-blue-600 dark:text-blue-400 hover:underline">
              Export to CSV
            </button>
          </div>
        </div>

        {/* Audit Log Entries */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
          {filteredLogs.length === 0 ? (
            <div className="p-8 text-center text-gray-600 dark:text-gray-400">
              No audit logs found matching your filters.
            </div>
          ) : (
            <div className="divide-y divide-gray-200 dark:divide-gray-700">
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
          )}
        </div>

        {/* Load More */}
        {filteredLogs.length > 0 && (
          <div className="mt-6 text-center">
            <button className="px-6 py-2 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 text-gray-900 dark:text-gray-100 font-medium rounded-md transition-colors">
              Load More
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
