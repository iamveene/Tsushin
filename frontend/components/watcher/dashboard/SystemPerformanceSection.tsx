'use client'

/**
 * System Performance Section
 *
 * Memory and semantic search stats with visual indicators.
 */

import AnimatedCounter from '@/components/charts/AnimatedCounter'
import RadialProgressChart from '@/components/charts/RadialProgressChart'
import { CHART_COLORS } from '@/components/charts/chartTheme'

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

interface SystemPerformanceSectionProps {
  memoryStats: MemoryStats | null
}

// SVG Icons
const DatabaseIcon = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <ellipse cx="12" cy="5" rx="9" ry="3" />
    <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
    <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
  </svg>
)

const UsersIcon = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
    <circle cx="9" cy="7" r="4" />
    <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
    <path d="M16 3.13a4 4 0 0 1 0 7.75" />
  </svg>
)

const MemoryIcon = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <rect x="2" y="6" width="20" height="12" rx="2" />
    <path d="M6 12h.01" />
    <path d="M10 12h.01" />
    <path d="M14 12h.01" />
    <path d="M18 12h.01" />
    <path d="M6 6V4" />
    <path d="M10 6V4" />
    <path d="M14 6V4" />
    <path d="M18 6V4" />
    <path d="M6 18v2" />
    <path d="M10 18v2" />
    <path d="M14 18v2" />
    <path d="M18 18v2" />
  </svg>
)

const BrainIcon = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 4.44-2.54" />
    <path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-4.44-2.54" />
  </svg>
)

export default function SystemPerformanceSection({
  memoryStats,
}: SystemPerformanceSectionProps) {
  if (!memoryStats) {
    return null
  }

  const bufferUsagePercent = memoryStats.total_messages_cached > 0
    ? Math.min(
        (memoryStats.total_messages_cached /
          (memoryStats.ring_buffer_size * Math.max(memoryStats.senders_in_memory, 1))) *
          100,
        100
      )
    : 0

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
            className="text-tsushin-purple"
          >
            <path d="M12 2v4" />
            <path d="m16.24 7.76 2.83-2.83" />
            <path d="M20 12h-4" />
            <path d="m16.24 16.24 2.83 2.83" />
            <path d="M12 18v4" />
            <path d="m7.76 16.24-2.83 2.83" />
            <path d="M4 12H0" />
            <path d="m7.76 7.76-2.83-2.83" />
            <circle cx="12" cy="12" r="4" />
          </svg>
          System Performance
        </h2>

        {/* Semantic Search Status Badge */}
        {memoryStats.semantic_search_enabled ? (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-tsushin-success/10 border border-tsushin-success/30">
            <div className="w-2 h-2 rounded-full bg-tsushin-success animate-pulse" />
            <span className="text-xs font-medium text-tsushin-success">
              Semantic Search Active
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-tsushin-muted/10 border border-tsushin-border/30">
            <div className="w-2 h-2 rounded-full bg-tsushin-muted" />
            <span className="text-xs font-medium text-tsushin-muted">
              Semantic Search Disabled
            </span>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Ring Buffer */}
        <div className="group relative overflow-hidden rounded-xl p-5 bg-gradient-to-br from-tsushin-surface to-transparent border border-tsushin-border/30 hover:border-tsushin-purple/30 transition-all">
          <div className="flex items-center justify-between mb-4">
            <div className="w-10 h-10 rounded-lg bg-tsushin-purple/10 flex items-center justify-center text-tsushin-purple">
              <DatabaseIcon />
            </div>
            <RadialProgressChart
              value={bufferUsagePercent}
              size={48}
              strokeWidth={5}
              color={CHART_COLORS.purple}
              showValue={false}
            />
          </div>
          <div>
            <p className="text-sm font-medium text-tsushin-slate">Ring Buffer</p>
            <p className="text-2xl font-display font-bold text-white mt-1">
              {memoryStats.ring_buffer_size}
            </p>
            <p className="text-xs text-tsushin-muted">msgs per sender</p>
          </div>
        </div>

        {/* Active Senders */}
        <div className="group relative overflow-hidden rounded-xl p-5 bg-gradient-to-br from-tsushin-surface to-transparent border border-tsushin-border/30 hover:border-tsushin-accent/30 transition-all">
          <div className="flex items-center justify-between mb-4">
            <div className="w-10 h-10 rounded-lg bg-tsushin-accent/10 flex items-center justify-center text-tsushin-accent">
              <UsersIcon />
            </div>
          </div>
          <div>
            <p className="text-sm font-medium text-tsushin-slate">Active Senders</p>
            <p className="text-2xl font-display font-bold text-white mt-1">
              <AnimatedCounter value={memoryStats.senders_in_memory} />
            </p>
            <p className="text-xs text-tsushin-muted">in memory</p>
          </div>
        </div>

        {/* Messages Cached */}
        <div className="group relative overflow-hidden rounded-xl p-5 bg-gradient-to-br from-tsushin-surface to-transparent border border-tsushin-border/30 hover:border-tsushin-indigo/30 transition-all">
          <div className="flex items-center justify-between mb-4">
            <div className="w-10 h-10 rounded-lg bg-tsushin-indigo/10 flex items-center justify-center text-tsushin-indigo">
              <MemoryIcon />
            </div>
          </div>
          <div>
            <p className="text-sm font-medium text-tsushin-slate">Messages Cached</p>
            <p className="text-2xl font-display font-bold text-white mt-1">
              <AnimatedCounter value={memoryStats.total_messages_cached} />
            </p>
            <p className="text-xs text-tsushin-muted">total processed</p>
          </div>
        </div>

        {/* Vector Embeddings */}
        {memoryStats.vector_store ? (
          <div className="group relative overflow-hidden rounded-xl p-5 bg-gradient-to-br from-tsushin-indigo/5 to-tsushin-purple/5 border border-tsushin-indigo/30 hover:border-tsushin-indigo/50 transition-all">
            <div className="flex items-center justify-between mb-4">
              <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-tsushin-indigo/20 to-tsushin-purple/20 flex items-center justify-center text-tsushin-indigo">
                <BrainIcon />
              </div>
              <div className="flex items-center gap-1">
                <div className="w-1.5 h-1.5 rounded-full bg-tsushin-success animate-pulse" />
                <span className="text-[10px] text-tsushin-success font-medium">AI</span>
              </div>
            </div>
            <div>
              <p className="text-sm font-medium text-tsushin-indigo-glow">
                Vector Embeddings
              </p>
              <p className="text-2xl font-display font-bold text-white mt-1">
                <AnimatedCounter value={memoryStats.vector_store.total_embeddings} />
              </p>
              <p className="text-xs text-tsushin-slate">AI-indexed messages</p>
            </div>
          </div>
        ) : (
          <div className="group relative overflow-hidden rounded-xl p-5 bg-gradient-to-br from-tsushin-surface to-transparent border border-tsushin-border/30">
            <div className="flex items-center justify-between mb-4">
              <div className="w-10 h-10 rounded-lg bg-tsushin-muted/10 flex items-center justify-center text-tsushin-muted">
                <BrainIcon />
              </div>
            </div>
            <div>
              <p className="text-sm font-medium text-tsushin-muted">Vector Store</p>
              <p className="text-lg font-display font-medium text-tsushin-muted mt-2">
                Not configured
              </p>
              <p className="text-xs text-tsushin-muted">Enable for AI search</p>
            </div>
          </div>
        )}
      </div>

      {/* Semantic Search Info Banner */}
      {memoryStats.semantic_search_enabled && memoryStats.vector_store && (
        <div className="mt-4 pt-4 border-t border-tsushin-border/20">
          <div className="flex items-start gap-3 text-sm">
            <div className="w-5 h-5 rounded-full bg-tsushin-warning/10 flex items-center justify-center flex-shrink-0 mt-0.5">
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="currentColor"
                className="text-tsushin-warning"
              >
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z" />
              </svg>
            </div>
            <p className="text-tsushin-slate">
              <span className="font-medium text-white">Semantic search is active:</span>{' '}
              The agent can find relevant past messages based on meaning, not just keywords.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
