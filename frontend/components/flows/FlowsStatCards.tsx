'use client'

/**
 * Flows Stat Cards Component
 *
 * Compact enterprise-grade stat cards for the Flows page with:
 * - Gradient backgrounds
 * - SVG icons with colored backgrounds
 * - Animated counters
 * - Hover glow effects
 * - Click-to-filter functionality
 */

import AnimatedCounter from '@/components/charts/AnimatedCounter'

// SVG Icons (smaller 18x18)
const ConversationIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
  </svg>
)

const NotificationIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
    <path d="M13.73 21a2 2 0 0 1-3.46 0" />
  </svg>
)

const WorkflowIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
  </svg>
)

const TaskIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
  </svg>
)

const CheckCircleIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
    <polyline points="22 4 12 14.01 9 11.01" />
  </svg>
)

const CircleIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" />
  </svg>
)

const ActivityIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
  </svg>
)

const ThreadsIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
  </svg>
)

type FlowType = 'conversation' | 'notification' | 'workflow' | 'task'

interface CardConfig {
  key: string
  label: string
  Icon: React.FC
  color: string
  hoverBorder: string
  iconBg: string
  glowColor: string
  type: 'flow' | 'status' | 'metric'
  filterValue?: string
}

const CARD_CONFIGS: CardConfig[] = [
  // Flow Types
  {
    key: 'conversation',
    label: 'Conversation',
    Icon: ConversationIcon,
    color: 'text-tsushin-accent',
    hoverBorder: 'hover:border-tsushin-accent/40',
    iconBg: 'bg-tsushin-accent/10',
    glowColor: 'from-tsushin-accent/5',
    type: 'flow',
    filterValue: 'conversation',
  },
  {
    key: 'notification',
    label: 'Notification',
    Icon: NotificationIcon,
    color: 'text-tsushin-warning',
    hoverBorder: 'hover:border-tsushin-warning/40',
    iconBg: 'bg-tsushin-warning/10',
    glowColor: 'from-tsushin-warning/5',
    type: 'flow',
    filterValue: 'notification',
  },
  {
    key: 'workflow',
    label: 'Workflow',
    Icon: WorkflowIcon,
    color: 'text-purple-400',
    hoverBorder: 'hover:border-purple-400/40',
    iconBg: 'bg-purple-400/10',
    glowColor: 'from-purple-400/5',
    type: 'flow',
    filterValue: 'workflow',
  },
  {
    key: 'task',
    label: 'Task',
    Icon: TaskIcon,
    color: 'text-tsushin-indigo',
    hoverBorder: 'hover:border-tsushin-indigo/40',
    iconBg: 'bg-tsushin-indigo/10',
    glowColor: 'from-tsushin-indigo/5',
    type: 'flow',
    filterValue: 'task',
  },
  // Status
  {
    key: 'enabled',
    label: 'Enabled',
    Icon: CheckCircleIcon,
    color: 'text-tsushin-success',
    hoverBorder: 'hover:border-tsushin-success/40',
    iconBg: 'bg-tsushin-success/10',
    glowColor: 'from-tsushin-success/5',
    type: 'status',
    filterValue: 'enabled',
  },
  {
    key: 'disabled',
    label: 'Disabled',
    Icon: CircleIcon,
    color: 'text-tsushin-muted',
    hoverBorder: 'hover:border-tsushin-muted/40',
    iconBg: 'bg-tsushin-muted/10',
    glowColor: 'from-tsushin-muted/5',
    type: 'status',
    filterValue: 'disabled',
  },
  // Metrics
  {
    key: 'running',
    label: 'Running',
    Icon: ActivityIcon,
    color: 'text-tsushin-accent',
    hoverBorder: 'hover:border-tsushin-accent/40',
    iconBg: 'bg-tsushin-accent/10',
    glowColor: 'from-tsushin-accent/5',
    type: 'metric',
  },
  {
    key: 'threads',
    label: 'Threads',
    Icon: ThreadsIcon,
    color: 'text-purple-400',
    hoverBorder: 'hover:border-purple-400/40',
    iconBg: 'bg-purple-400/10',
    glowColor: 'from-purple-400/5',
    type: 'metric',
  },
]

interface FlowsStatCardsProps {
  stats: {
    totalFlows: number
    activeFlows: number
    inactiveFlows: number
    runningRuns: number
    activeThreads: number
    byType: Record<string, number>
  }
  typeFilter: FlowType | ''
  statusFilter: string
  onTypeFilterChange: (type: FlowType | '') => void
  onStatusFilterChange: (status: string) => void
  loading?: boolean
}

export default function FlowsStatCards({
  stats,
  typeFilter,
  statusFilter,
  onTypeFilterChange,
  onStatusFilterChange,
  loading = false,
}: FlowsStatCardsProps) {

  const getValue = (config: CardConfig): number => {
    if (config.type === 'flow') {
      return stats.byType[config.key] || 0
    }
    if (config.key === 'enabled') return stats.activeFlows
    if (config.key === 'disabled') return stats.inactiveFlows
    if (config.key === 'running') return stats.runningRuns
    if (config.key === 'threads') return stats.activeThreads
    return 0
  }

  const isActive = (config: CardConfig): boolean => {
    if (config.type === 'flow') return typeFilter === config.filterValue
    if (config.type === 'status') return statusFilter === config.filterValue
    return false
  }

  const handleClick = (config: CardConfig) => {
    if (config.type === 'flow') {
      onTypeFilterChange(typeFilter === config.filterValue ? '' : config.filterValue as FlowType)
    } else if (config.type === 'status') {
      onStatusFilterChange(statusFilter === config.filterValue ? '' : config.filterValue!)
    }
  }

  return (
    <div className={`grid grid-cols-4 md:grid-cols-8 gap-3 transition-opacity duration-200 ${loading ? 'opacity-60' : ''}`}>
      {CARD_CONFIGS.map((config) => {
        const active = isActive(config)
        const value = getValue(config)
        const Icon = config.Icon
        const isClickable = config.type !== 'metric'

        const CardWrapper = isClickable ? 'button' : 'div'

        return (
          <CardWrapper
            key={config.key}
            onClick={isClickable ? () => handleClick(config) : undefined}
            className={`group relative overflow-hidden rounded-xl p-3 text-center transition-all
              bg-gradient-to-br from-tsushin-surface to-transparent
              border ${active
                ? `border-${config.color.replace('text-', '')}/50 shadow-lg shadow-${config.color.replace('text-', '')}/10`
                : `border-tsushin-border/30 ${config.hoverBorder}`
              } ${isClickable ? 'cursor-pointer' : ''}`}
          >
            {/* Icon */}
            <div className={`w-8 h-8 mx-auto rounded-lg ${config.iconBg} flex items-center justify-center ${config.color} group-hover:scale-110 transition-transform mb-2`}>
              <Icon />
            </div>

            {/* Value */}
            <div className={`text-xl font-bold ${active ? config.color : 'text-white'}`}>
              <AnimatedCounter value={value} />
            </div>

            {/* Label */}
            <div className="text-xs text-tsushin-slate group-hover:text-tsushin-fog transition-colors">
              {config.label}
            </div>

            {/* Live indicator for running */}
            {config.key === 'running' && value > 0 && (
              <span className="absolute top-2 right-2 w-2 h-2 rounded-full bg-tsushin-accent animate-pulse" />
            )}

            {/* Hover glow effect */}
            <div className={`absolute inset-0 bg-gradient-to-r ${config.glowColor} to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none`} />
          </CardWrapper>
        )
      })}
    </div>
  )
}
