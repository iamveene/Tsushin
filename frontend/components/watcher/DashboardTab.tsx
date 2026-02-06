'use client'

/**
 * Dashboard Tab - High-Level System Analytics
 *
 * Premium analytics dashboard with modern visualizations:
 * - Hero KPI section with animated counters and sparklines
 * - Activity timeline with time-series charts
 * - Distribution charts (channels, status, tools)
 * - System performance metrics
 */

import { useEffect, useState, useMemo } from 'react'
import { api, type Message, type AgentRun } from '@/lib/client'

// Dashboard sections
import HeroKPISection from './dashboard/HeroKPISection'
import ActivityTimelineSection from './dashboard/ActivityTimelineSection'
import DistributionChartsSection from './dashboard/DistributionChartsSection'
import SystemPerformanceSection from './dashboard/SystemPerformanceSection'

interface MemoryStats {
  semantic_search_enabled: boolean
  ring_buffer_size: number
  senders_in_memory: number
  total_messages_cached: number
  vector_store?: {
    total_embeddings: number
    collection_name: string
    persist_directory: string
  }
}

export default function DashboardTab() {
  const [messages, setMessages] = useState<Message[]>([])
  const [agentRuns, setAgentRuns] = useState<AgentRun[]>([])
  const [memoryStats, setMemoryStats] = useState<MemoryStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [totalMessages, setTotalMessages] = useState(0)
  const [totalAgentRuns, setTotalAgentRuns] = useState(0)

  useEffect(() => {
    loadData()

    // Polling every 5 seconds for dashboard updates
    const interval = setInterval(loadData, 5000)

    // Listen for global refresh events
    const handleRefresh = () => {
      console.log('[DashboardTab] Refresh event received')
      loadData()
    }
    window.addEventListener('tsushin:refresh', handleRefresh)

    return () => {
      clearInterval(interval)
      window.removeEventListener('tsushin:refresh', handleRefresh)
    }
  }, [])

  const loadData = async () => {
    try {
      const [msgs, runs, msgCount, runsCount, stats] = await Promise.all([
        api.getMessages(50),
        api.getAgentRuns(50),
        api.getMessageCount(),
        api.getAgentRunsCount(),
        api.getMemoryStats(),
      ])
      setMessages(msgs)
      setAgentRuns(runs)
      setTotalMessages(msgCount.total)
      setTotalAgentRuns(runsCount.total)
      setMemoryStats(stats)
    } catch (err) {
      console.error('Failed to load data:', err)
    } finally {
      setLoading(false)
    }
  }

  // Computed metrics
  const metrics = useMemo(() => {
    const successfulRuns = agentRuns.filter((r) => r.status === 'success').length
    const failedRuns = agentRuns.filter((r) => r.status === 'failed').length
    const successRate =
      agentRuns.length > 0
        ? Math.round((successfulRuns / agentRuns.length) * 100)
        : 0
    const matchedMessages = messages.filter((m) => m.matched_filter).length

    // Calculate average execution time
    const runsWithTime = agentRuns.filter((r) => r.execution_time_ms != null)
    const avgExecutionTime =
      runsWithTime.length > 0
        ? runsWithTime.reduce((sum, r) => sum + (r.execution_time_ms || 0), 0) /
          runsWithTime.length
        : 0

    return {
      successfulRuns,
      failedRuns,
      successRate,
      matchedMessages,
      avgExecutionTime,
    }
  }, [messages, agentRuns])

  // Loading skeleton
  if (loading) {
    return (
      <div className="space-y-6 animate-fade-in">
        {/* Hero skeleton */}
        <div className="glass-card rounded-xl p-6 border-t-2 border-t-tsushin-indigo/20">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {[...Array(4)].map((_, i) => (
              <div
                key={i}
                className="rounded-xl p-5 bg-tsushin-surface border border-tsushin-border/30"
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="w-10 h-10 rounded-lg skeleton" />
                  <div className="w-16 h-7 rounded skeleton" />
                </div>
                <div className="space-y-2">
                  <div className="w-24 h-4 rounded skeleton" />
                  <div className="w-20 h-8 rounded skeleton" />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Timeline skeleton */}
        <div className="glass-card rounded-xl p-6">
          <div className="flex items-center justify-between mb-6">
            <div className="w-40 h-6 rounded skeleton" />
            <div className="w-32 h-8 rounded skeleton" />
          </div>
          <div className="h-[280px] rounded skeleton" />
        </div>

        {/* Distribution skeleton */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="glass-card rounded-xl p-6">
            <div className="w-40 h-5 rounded skeleton mb-4" />
            <div className="h-[240px] rounded skeleton" />
          </div>
          <div className="space-y-6">
            <div className="glass-card rounded-xl p-6">
              <div className="w-36 h-5 rounded skeleton mb-4" />
              <div className="h-24 rounded skeleton" />
            </div>
            <div className="glass-card rounded-xl p-6">
              <div className="w-28 h-5 rounded skeleton mb-4" />
              <div className="h-32 rounded skeleton" />
            </div>
          </div>
        </div>

        {/* Performance skeleton */}
        <div className="glass-card rounded-xl p-6">
          <div className="flex items-center justify-between mb-6">
            <div className="w-44 h-6 rounded skeleton" />
            <div className="w-36 h-7 rounded-full skeleton" />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => (
              <div
                key={i}
                className="rounded-xl p-5 bg-tsushin-surface border border-tsushin-border/30"
              >
                <div className="w-10 h-10 rounded-lg skeleton mb-4" />
                <div className="space-y-2">
                  <div className="w-20 h-4 rounded skeleton" />
                  <div className="w-16 h-7 rounded skeleton" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Hero KPI Section */}
      <HeroKPISection
        totalMessages={totalMessages}
        totalAgentRuns={totalAgentRuns}
        matchedFilters={metrics.matchedMessages}
        successRate={metrics.successRate}
        avgExecutionTime={metrics.avgExecutionTime}
      />

      {/* Activity Timeline */}
      <ActivityTimelineSection messages={messages} agentRuns={agentRuns} />

      {/* Distribution Charts */}
      <DistributionChartsSection messages={messages} agentRuns={agentRuns} />

      {/* System Performance */}
      <SystemPerformanceSection memoryStats={memoryStats} />
    </div>
  )
}
