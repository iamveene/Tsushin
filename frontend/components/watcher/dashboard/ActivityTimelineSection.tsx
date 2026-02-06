'use client'

/**
 * Activity Timeline Section
 *
 * Time-series area chart showing messages and agent runs over time.
 * Includes period selector (24H, 7D, 30D).
 */

import { useState, useMemo } from 'react'
import AreaChart from '@/components/charts/AreaChart'
import type { Message, AgentRun } from '@/lib/client'

interface ActivityTimelineSectionProps {
  messages: Message[]
  agentRuns: AgentRun[]
}

type TimePeriod = '24h' | '7d' | '30d'

// Aggregate data into time buckets
function aggregateByTime(
  messages: Message[],
  agentRuns: AgentRun[],
  period: TimePeriod
): { time: string; messages: number; agentRuns: number }[] {
  const now = new Date()
  let bucketSize: number // in milliseconds
  let bucketCount: number
  let formatTime: (date: Date) => string

  switch (period) {
    case '24h':
      bucketSize = 60 * 60 * 1000 // 1 hour
      bucketCount = 24
      formatTime = (d) => `${d.getHours().toString().padStart(2, '0')}:00`
      break
    case '7d':
      bucketSize = 24 * 60 * 60 * 1000 // 1 day
      bucketCount = 7
      formatTime = (d) => d.toLocaleDateString('en-US', { weekday: 'short' })
      break
    case '30d':
      bucketSize = 24 * 60 * 60 * 1000 // 1 day
      bucketCount = 30
      formatTime = (d) => `${d.getMonth() + 1}/${d.getDate()}`
      break
  }

  // Initialize buckets
  const buckets: Map<number, { messages: number; agentRuns: number }> = new Map()
  for (let i = 0; i < bucketCount; i++) {
    const bucketTime = now.getTime() - (bucketCount - 1 - i) * bucketSize
    buckets.set(Math.floor(bucketTime / bucketSize) * bucketSize, {
      messages: 0,
      agentRuns: 0,
    })
  }

  // Aggregate messages
  messages.forEach((msg) => {
    const timestamp = new Date(msg.timestamp || msg.seen_at).getTime()
    const bucketKey = Math.floor(timestamp / bucketSize) * bucketSize
    const bucket = buckets.get(bucketKey)
    if (bucket) {
      bucket.messages++
    }
  })

  // Aggregate agent runs
  agentRuns.forEach((run) => {
    const timestamp = new Date(run.created_at).getTime()
    const bucketKey = Math.floor(timestamp / bucketSize) * bucketSize
    const bucket = buckets.get(bucketKey)
    if (bucket) {
      bucket.agentRuns++
    }
  })

  // Convert to array with formatted time labels
  return Array.from(buckets.entries())
    .sort(([a], [b]) => a - b)
    .map(([timestamp, data]) => ({
      time: formatTime(new Date(timestamp)),
      messages: data.messages,
      agentRuns: data.agentRuns,
    }))
}

export default function ActivityTimelineSection({
  messages,
  agentRuns,
}: ActivityTimelineSectionProps) {
  const [period, setPeriod] = useState<TimePeriod>('24h')

  const chartData = useMemo(
    () => aggregateByTime(messages, agentRuns, period),
    [messages, agentRuns, period]
  )

  const series = [
    { key: 'messages', name: 'Messages', color: 'accent' },
    { key: 'agentRuns', name: 'Agent Runs', color: 'primary' },
  ]

  const hasData = messages.length > 0 || agentRuns.length > 0

  return (
    <div className="glass-card rounded-xl p-6 animate-fade-in">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-lg font-display font-semibold text-white flex items-center gap-2">
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="text-tsushin-accent"
          >
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
          </svg>
          Activity Timeline
        </h2>

        {/* Period Selector */}
        <div className="flex items-center gap-1 p-1 rounded-lg bg-tsushin-surface border border-tsushin-border/30">
          {(['24h', '7d', '30d'] as TimePeriod[]).map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
                period === p
                  ? 'bg-tsushin-indigo text-white'
                  : 'text-tsushin-slate hover:text-white hover:bg-tsushin-surface-alt'
              }`}
            >
              {p.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {hasData ? (
        <AreaChart
          data={chartData}
          series={series}
          xAxisKey="time"
          height={280}
          showGrid={true}
          showLegend={true}
          stacked={false}
        />
      ) : (
        <div className="flex flex-col items-center justify-center h-[280px] text-tsushin-slate">
          <svg
            width="48"
            height="48"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            className="mb-3 opacity-50"
          >
            <path d="M3 3v18h18" />
            <path d="M18 17V9" />
            <path d="M13 17V5" />
            <path d="M8 17v-3" />
          </svg>
          <p className="text-sm">No activity data available</p>
          <p className="text-xs text-tsushin-muted mt-1">
            Data will appear as messages and agent runs are recorded
          </p>
        </div>
      )}
    </div>
  )
}
