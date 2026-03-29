'use client'

/**
 * Audit Logs Page — v0.6.0 Enhanced
 * Tenant-scoped audit event viewer with filters, stats, and CSV export.
 */

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { useAuth } from '@/contexts/AuthContext'
import { api } from '@/lib/client'
import AuditLogEntry from '@/components/rbac/AuditLogEntry'

interface AuditEvent {
  id: number
  action: string
  user_id: number | null
  user_name: string | null
  resource_type: string | null
  resource_id: string | null
  details: Record<string, unknown> | null
  ip_address: string | null
  channel: string | null
  severity: string
  created_at: string
}

interface AuditStats {
  events_today: number
  events_this_week: number
  critical_count: number
  top_actors: Array<{ user_id: number | null; user_name: string; event_count: number }>
  by_category: Record<string, number>
}

const PAGE_SIZE = 50

const ACTION_CATEGORIES = [
  { value: '', label: 'All Actions' },
  { value: 'auth', label: 'Authentication' },
  { value: 'agent', label: 'Agents' },
  { value: 'flow', label: 'Flows' },
  { value: 'contact', label: 'Contacts' },
  { value: 'settings', label: 'Settings' },
  { value: 'security', label: 'Security' },
  { value: 'api_client', label: 'API Clients' },
  { value: 'skill', label: 'Custom Skills' },
  { value: 'mcp', label: 'MCP Servers' },
  { value: 'team', label: 'Team' },
]

const SEVERITY_OPTIONS = [
  { value: '', label: 'All Severities' },
  { value: 'info', label: 'Info' },
  { value: 'warning', label: 'Warning' },
  { value: 'critical', label: 'Critical' },
]

const CHANNEL_OPTIONS = [
  { value: '', label: 'All Channels' },
  { value: 'web', label: 'Web' },
  { value: 'api', label: 'API' },
  { value: 'whatsapp', label: 'WhatsApp' },
  { value: 'telegram', label: 'Telegram' },
  { value: 'system', label: 'System' },
]

export default function AuditLogsPage() {
  const { hasPermission } = useAuth()
  const [events, setEvents] = useState<AuditEvent[]>([])
  const [total, setTotal] = useState(0)
  const [stats, setStats] = useState<AuditStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)

  // Filters
  const [filterAction, setFilterAction] = useState('')
  const [filterSeverity, setFilterSeverity] = useState('')
  const [filterChannel, setFilterChannel] = useState('')
  const [filterFromDate, setFilterFromDate] = useState('')
  const [filterToDate, setFilterToDate] = useState('')
  const [offset, setOffset] = useState(0)

  const fetchEvents = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await api.getAuditEvents({
        limit: PAGE_SIZE,
        offset,
        action: filterAction || undefined,
        severity: filterSeverity || undefined,
        channel: filterChannel || undefined,
        from_date: filterFromDate || undefined,
        to_date: filterToDate || undefined,
      })
      if (offset === 0) {
        setEvents(data.events)
      } else {
        setEvents((prev) => [...prev, ...data.events])
      }
      setTotal(data.total)
    } catch (err) {
      console.error('Failed to fetch audit events:', err)
      setError('Failed to load audit events')
    } finally {
      setLoading(false)
    }
  }, [offset, filterAction, filterSeverity, filterChannel, filterFromDate, filterToDate])

  const fetchStats = useCallback(async () => {
    try {
      const data = await api.getAuditLogStats()
      setStats(data)
    } catch (err) {
      console.error('Failed to fetch audit stats:', err)
    }
  }, [])

  // Reset offset when filters change
  useEffect(() => {
    setOffset(0)
  }, [filterAction, filterSeverity, filterChannel, filterFromDate, filterToDate])

  useEffect(() => {
    if (hasPermission('audit.read')) {
      fetchEvents()
    }
  }, [fetchEvents, hasPermission])

  useEffect(() => {
    if (hasPermission('audit.read')) {
      fetchStats()
    }
  }, [fetchStats, hasPermission])

  const handleExport = async () => {
    try {
      setExporting(true)
      const blob = await api.exportAuditLogs({
        action: filterAction || undefined,
        severity: filterSeverity || undefined,
        channel: filterChannel || undefined,
        from_date: filterFromDate || undefined,
        to_date: filterToDate || undefined,
      })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `audit_logs_${new Date().toISOString().split('T')[0]}.csv`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
    } catch (err) {
      console.error('Failed to export audit logs:', err)
    } finally {
      setExporting(false)
    }
  }

  const handleFilterByAction = (action: string) => {
    setFilterAction(action.split('.')[0])
  }

  if (!hasPermission('audit.read')) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="bg-red-900/20 border border-red-800 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-red-100 mb-2">Access Denied</h3>
          <p className="text-sm text-red-200">You don&apos;t have permission to view audit logs.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-white">Audit Logs</h1>
            <p className="text-tsushin-slate mt-1">Track all activities in your organization</p>
          </div>
          {hasPermission('audit.read') && (
            <button
              onClick={handleExport}
              disabled={exporting}
              className="flex items-center gap-2 px-4 py-2 bg-teal-600 hover:bg-teal-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              {exporting ? 'Exporting...' : 'Export CSV'}
            </button>
          )}
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

        {/* Stats Bar */}
        {stats && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
            <div className="bg-tsushin-surface border border-white/10 rounded-lg p-4">
              <p className="text-sm text-tsushin-slate">Events Today</p>
              <p className="text-2xl font-bold text-white mt-1">{stats.events_today}</p>
            </div>
            <div className="bg-tsushin-surface border border-white/10 rounded-lg p-4">
              <p className="text-sm text-tsushin-slate">This Week</p>
              <p className="text-2xl font-bold text-white mt-1">{stats.events_this_week}</p>
            </div>
            <div className="bg-tsushin-surface border border-white/10 rounded-lg p-4">
              <p className="text-sm text-tsushin-slate">Critical Events</p>
              <p className={`text-2xl font-bold mt-1 ${stats.critical_count > 0 ? 'text-red-400' : 'text-white'}`}>
                {stats.critical_count}
              </p>
            </div>
          </div>
        )}

        {/* Filters */}
        <div className="bg-tsushin-surface border border-white/10 rounded-lg p-4 mb-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
            <div>
              <label className="block text-xs font-medium text-tsushin-slate mb-1">Action</label>
              <select
                value={filterAction}
                onChange={(e) => setFilterAction(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-white/10 rounded-md text-white bg-tsushin-surface"
              >
                {ACTION_CATEGORIES.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-tsushin-slate mb-1">Severity</label>
              <select
                value={filterSeverity}
                onChange={(e) => setFilterSeverity(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-white/10 rounded-md text-white bg-tsushin-surface"
              >
                {SEVERITY_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-tsushin-slate mb-1">Channel</label>
              <select
                value={filterChannel}
                onChange={(e) => setFilterChannel(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-white/10 rounded-md text-white bg-tsushin-surface"
              >
                {CHANNEL_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-tsushin-slate mb-1">From</label>
              <input
                type="date"
                value={filterFromDate}
                onChange={(e) => setFilterFromDate(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-white/10 rounded-md text-white bg-tsushin-surface"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-tsushin-slate mb-1">To</label>
              <input
                type="date"
                value={filterToDate}
                onChange={(e) => setFilterToDate(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-white/10 rounded-md text-white bg-tsushin-surface"
              />
            </div>
          </div>
          <div className="mt-3 flex items-center justify-between">
            <span className="text-xs text-tsushin-slate">
              Showing {events.length} of {total} events
            </span>
            {(filterAction || filterSeverity || filterChannel || filterFromDate || filterToDate) && (
              <button
                onClick={() => {
                  setFilterAction('')
                  setFilterSeverity('')
                  setFilterChannel('')
                  setFilterFromDate('')
                  setFilterToDate('')
                }}
                className="text-xs text-teal-400 hover:text-teal-300 transition-colors"
              >
                Clear filters
              </button>
            )}
          </div>
        </div>

        {/* Error State */}
        {error && (
          <div className="bg-red-900/20 border border-red-800 rounded-lg p-4 mb-6">
            <p className="text-sm text-red-200">{error}</p>
          </div>
        )}

        {/* Loading State */}
        {loading && events.length === 0 && (
          <div className="bg-tsushin-surface border border-white/10 rounded-lg p-8 text-center">
            <p className="text-tsushin-slate">Loading audit events...</p>
          </div>
        )}

        {/* Empty State */}
        {!loading && events.length === 0 && !error && (
          <div className="bg-tsushin-surface border border-white/10 rounded-lg p-8 text-center">
            <svg className="w-12 h-12 text-tsushin-slate mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <p className="text-tsushin-slate">No audit events found.</p>
            <p className="text-xs text-tsushin-slate/60 mt-1">Events will appear here as actions are performed in the platform.</p>
          </div>
        )}

        {/* Audit Event Entries */}
        {events.length > 0 && (
          <div className="bg-tsushin-surface border border-white/10 rounded-lg overflow-hidden">
            <div className="divide-y divide-white/5">
              {events.map((event) => (
                <AuditLogEntry
                  key={event.id}
                  action={event.action}
                  user={event.user_name || 'System'}
                  resource={event.resource_type && event.resource_id ? `${event.resource_type}/${event.resource_id}` : event.resource_type || undefined}
                  timestamp={event.created_at}
                  ipAddress={event.ip_address || undefined}
                  details={event.details ? JSON.stringify(event.details) : undefined}
                  severity={event.severity}
                  channel={event.channel || undefined}
                  onFilterAction={handleFilterByAction}
                />
              ))}
            </div>
          </div>
        )}

        {/* Load More */}
        {events.length < total && (
          <div className="mt-6 text-center">
            <button
              onClick={() => setOffset((prev) => prev + PAGE_SIZE)}
              disabled={loading}
              className="px-6 py-2 bg-white/10 hover:bg-white/15 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
            >
              {loading ? 'Loading...' : 'Load More'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
