'use client'

/**
 * Hero KPI Section
 *
 * Top metrics display with animated counters, sparklines, and radial gauges.
 * The visual hero of the dashboard.
 */

import AnimatedCounter from '@/components/charts/AnimatedCounter'
import SparklineChart, { generateSparklineData } from '@/components/charts/SparklineChart'
import RadialProgressChart from '@/components/charts/RadialProgressChart'
import { CHART_COLORS } from '@/components/charts/chartTheme'

// SVG Icons
const MessageIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
  </svg>
)

const AgentIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="11" width="18" height="10" rx="2" />
    <circle cx="12" cy="5" r="2" />
    <path d="M12 7v4" />
    <line x1="8" y1="16" x2="8" y2="16" />
    <line x1="16" y1="16" x2="16" y2="16" />
  </svg>
)

const FilterIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
  </svg>
)

const ClockIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" />
    <polyline points="12 6 12 12 16 14" />
  </svg>
)

interface HeroKPISectionProps {
  totalMessages: number
  totalAgentRuns: number
  matchedFilters: number
  successRate: number
  avgExecutionTime?: number // in milliseconds
  recentMessages?: number[]
  recentAgentRuns?: number[]
}

export default function HeroKPISection({
  totalMessages,
  totalAgentRuns,
  matchedFilters,
  successRate,
  avgExecutionTime = 0,
  recentMessages,
  recentAgentRuns,
}: HeroKPISectionProps) {
  // Generate sparkline data if not provided
  const messagesSparkline = recentMessages || generateSparklineData(totalMessages, 12, 'up')
  const agentRunsSparkline = recentAgentRuns || generateSparklineData(totalAgentRuns, 12, 'up')

  return (
    <div className="glass-card rounded-xl p-6 border-t-2 border-t-tsushin-indigo/50 animate-fade-in">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {/* Total Messages */}
        <div className="group relative overflow-hidden rounded-xl p-5 bg-gradient-to-br from-tsushin-surface to-transparent border border-tsushin-border/30 hover:border-tsushin-accent/30 transition-all">
          <div className="flex items-start justify-between mb-3">
            <div className="w-10 h-10 rounded-lg bg-tsushin-accent/10 flex items-center justify-center text-tsushin-accent group-hover:scale-110 transition-transform">
              <MessageIcon />
            </div>
            <SparklineChart
              data={messagesSparkline}
              color="accent"
              width={70}
              height={28}
            />
          </div>
          <div className="space-y-1">
            <p className="text-sm font-medium text-tsushin-slate">Total Messages</p>
            <p className="text-3xl font-display font-bold text-white">
              <AnimatedCounter value={totalMessages} />
            </p>
          </div>
          {/* Subtle glow effect on hover */}
          <div className="absolute inset-0 bg-gradient-to-r from-tsushin-accent/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
        </div>

        {/* Total Agent Runs */}
        <div className="group relative overflow-hidden rounded-xl p-5 bg-gradient-to-br from-tsushin-surface to-transparent border border-tsushin-border/30 hover:border-tsushin-indigo/30 transition-all">
          <div className="flex items-start justify-between mb-3">
            <div className="w-10 h-10 rounded-lg bg-tsushin-indigo/10 flex items-center justify-center text-tsushin-indigo group-hover:scale-110 transition-transform">
              <AgentIcon />
            </div>
            <SparklineChart
              data={agentRunsSparkline}
              color="primary"
              width={70}
              height={28}
            />
          </div>
          <div className="space-y-1">
            <p className="text-sm font-medium text-tsushin-slate">Agent Runs</p>
            <p className="text-3xl font-display font-bold text-white">
              <AnimatedCounter value={totalAgentRuns} />
            </p>
          </div>
          <div className="absolute inset-0 bg-gradient-to-r from-tsushin-indigo/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
        </div>

        {/* Success Rate - Radial Gauge */}
        <div className="group relative overflow-hidden rounded-xl p-5 bg-gradient-to-br from-tsushin-surface to-transparent border border-tsushin-border/30 hover:border-tsushin-success/30 transition-all">
          <div className="flex items-center justify-between h-full">
            <div className="space-y-1">
              <p className="text-sm font-medium text-tsushin-slate">Success Rate</p>
              <div className="flex items-center gap-2 mt-2">
                <div className="w-8 h-8 rounded-lg bg-tsushin-success/10 flex items-center justify-center text-tsushin-success">
                  <FilterIcon />
                </div>
                <span className="text-xs text-tsushin-muted">
                  {matchedFilters} matched
                </span>
              </div>
            </div>
            <RadialProgressChart
              value={successRate}
              size={90}
              strokeWidth={8}
              label="runs"
            />
          </div>
          <div className="absolute inset-0 bg-gradient-to-r from-tsushin-success/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
        </div>

        {/* Average Execution Time */}
        <div className="group relative overflow-hidden rounded-xl p-5 bg-gradient-to-br from-tsushin-surface to-transparent border border-tsushin-border/30 hover:border-tsushin-warning/30 transition-all">
          <div className="flex items-start justify-between mb-3">
            <div className="w-10 h-10 rounded-lg bg-tsushin-warning/10 flex items-center justify-center text-tsushin-warning group-hover:scale-110 transition-transform">
              <ClockIcon />
            </div>
          </div>
          <div className="space-y-1">
            <p className="text-sm font-medium text-tsushin-slate">Avg Response</p>
            <p className="text-3xl font-display font-bold text-white">
              {avgExecutionTime > 0 ? (
                <AnimatedCounter
                  value={avgExecutionTime / 1000}
                  format="raw"
                  decimals={1}
                  suffix="s"
                />
              ) : (
                <span className="text-tsushin-muted">--</span>
              )}
            </p>
            {avgExecutionTime > 0 && (
              <p className="text-xs text-tsushin-muted">
                {avgExecutionTime < 1000 ? 'Excellent' : avgExecutionTime < 3000 ? 'Good' : 'Slow'}
              </p>
            )}
          </div>
          <div className="absolute inset-0 bg-gradient-to-r from-tsushin-warning/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
        </div>
      </div>
    </div>
  )
}
