'use client'

/**
 * Distribution Charts Section
 *
 * Grid of distribution visualizations:
 * - Channel distribution (donut)
 * - Agent status (horizontal bars)
 * - Tool usage (horizontal bars)
 * - Filter match rate (radial)
 */

import DonutChart from '@/components/charts/DonutChart'
import HorizontalBarChart from '@/components/charts/HorizontalBarChart'
import RadialProgressChart from '@/components/charts/RadialProgressChart'
import { CHANNEL_COLORS, STATUS_COLORS, CHART_COLORS } from '@/components/charts/chartTheme'
import type { Message, AgentRun } from '@/lib/client'

interface DistributionChartsSectionProps {
  messages: Message[]
  agentRuns: AgentRun[]
}

export default function DistributionChartsSection({
  messages,
  agentRuns,
}: DistributionChartsSectionProps) {
  // Channel distribution
  const channelStats = messages.reduce(
    (acc, msg) => {
      const channel = msg.channel || 'unknown'
      acc[channel] = (acc[channel] || 0) + 1
      return acc
    },
    {} as Record<string, number>
  )

  const channelData = Object.entries(channelStats).map(([name, value]) => ({
    name: name.charAt(0).toUpperCase() + name.slice(1),
    value,
    color: CHANNEL_COLORS[name] || CHANNEL_COLORS.unknown,
  }))

  // Agent status
  const successfulRuns = agentRuns.filter((r) => r.status === 'success').length
  const failedRuns = agentRuns.filter((r) => r.status === 'failed').length

  const statusData = [
    { name: 'Success', value: successfulRuns, color: STATUS_COLORS.success },
    { name: 'Failed', value: failedRuns, color: STATUS_COLORS.failed },
  ]

  // Tool usage
  const toolUsage = agentRuns.reduce(
    (acc, run) => {
      const tool = run.tool_used || 'No Tool'
      acc[tool] = (acc[tool] || 0) + 1
      return acc
    },
    {} as Record<string, number>
  )

  const toolData = Object.entries(toolUsage).map(([name, value]) => ({
    name,
    value,
  }))

  // Filter match rate
  const matchedMessages = messages.filter((m) => m.matched_filter).length
  const matchRate =
    messages.length > 0 ? (matchedMessages / messages.length) * 100 : 0

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 animate-fade-in">
      {/* Left Column - Channel Distribution */}
      <div className="glass-card rounded-xl p-6">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            className="text-tsushin-purple"
          >
            <path d="M12 20V10" />
            <path d="M18 20V4" />
            <path d="M6 20v-4" />
          </svg>
          Channel Distribution
        </h3>
        <div className="flex justify-center">
          <DonutChart
            data={channelData}
            size={200}
            innerRadius={50}
            outerRadius={75}
            centerValue={messages.length.toString()}
            centerLabel="messages"
            showLegend={true}
          />
        </div>
      </div>

      {/* Right Column - Status & Tools */}
      <div className="space-y-6">
        {/* Agent Status */}
        <div className="glass-card rounded-xl p-6">
          <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className="text-tsushin-success"
            >
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
            Agent Performance
          </h3>
          <div className="flex items-center gap-6">
            <div className="flex-1">
              <HorizontalBarChart
                data={statusData}
                showPercentage={true}
                showValue={true}
                barHeight={20}
                maxBars={3}
              />
            </div>
            <RadialProgressChart
              value={agentRuns.length > 0 ? (successfulRuns / agentRuns.length) * 100 : 0}
              size={80}
              strokeWidth={8}
              label="success"
            />
          </div>
        </div>

        {/* Tool Usage */}
        <div className="glass-card rounded-xl p-6">
          <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className="text-tsushin-indigo"
            >
              <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
            </svg>
            Tool Usage
          </h3>
          <HorizontalBarChart
            data={toolData}
            showPercentage={true}
            showValue={true}
            barHeight={18}
            maxBars={5}
          />
        </div>
      </div>

      {/* Filter Match Rate - Full Width */}
      <div className="lg:col-span-2 glass-card rounded-xl p-6">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-white flex items-center gap-2">
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                className="text-tsushin-warning"
              >
                <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
              </svg>
              Filter Match Rate
            </h3>
            <p className="text-xs text-tsushin-muted mt-1">
              {matchedMessages} of {messages.length} messages matched configured filters
            </p>
          </div>

          <div className="flex items-center gap-8">
            {/* Stats */}
            <div className="text-right">
              <div className="flex items-center gap-4">
                <div>
                  <p className="text-2xl font-display font-bold text-tsushin-success">
                    {matchedMessages}
                  </p>
                  <p className="text-xs text-tsushin-muted">Matched</p>
                </div>
                <div className="w-px h-10 bg-tsushin-border/30" />
                <div>
                  <p className="text-2xl font-display font-bold text-tsushin-muted">
                    {messages.length - matchedMessages}
                  </p>
                  <p className="text-xs text-tsushin-muted">Unmatched</p>
                </div>
              </div>
            </div>

            {/* Radial */}
            <RadialProgressChart
              value={matchRate}
              size={100}
              strokeWidth={10}
              color={CHART_COLORS.warning}
              label="match rate"
            />
          </div>
        </div>
      </div>
    </div>
  )
}
