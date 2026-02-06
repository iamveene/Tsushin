/**
 * Tsushin Chart Theme Configuration
 *
 * Shared color palette and styling constants for all chart components.
 * Matches the Tsushin design system used in Graph View.
 */

// Primary chart colors
export const CHART_COLORS = {
  primary: '#3C5AFE',     // tsushin-indigo
  success: '#3FB950',     // green
  warning: '#D29922',     // amber
  danger: '#EE3E2D',      // red/vermilion
  accent: '#00D9FF',      // cyan
  muted: '#484F58',       // gray
  purple: '#8B5CF6',      // violet
  pink: '#EC4899',        // pink
  teal: '#14B8A6',        // teal
  slate: '#8B929E',       // slate text
} as const

// Channel-specific colors
export const CHANNEL_COLORS: Record<string, string> = {
  whatsapp: '#25D366',
  telegram: '#0088CC',
  playground: '#8B5CF6',
  unknown: '#6B7280',
}

// Status colors
export const STATUS_COLORS = {
  success: '#3FB950',
  failed: '#EE3E2D',
  pending: '#D29922',
  running: '#3C5AFE',
} as const

// Chart background and grid colors
export const CHART_BACKGROUND = {
  surface: '#161B22',
  surfaceAlt: '#1C2128',
  grid: 'rgba(139, 146, 158, 0.1)',
  gridStrong: 'rgba(139, 146, 158, 0.2)',
  border: 'rgba(139, 146, 158, 0.3)',
} as const

// Gradient definitions for area charts
export const CHART_GRADIENTS = {
  primary: {
    start: 'rgba(60, 90, 254, 0.4)',
    end: 'rgba(60, 90, 254, 0.0)',
  },
  success: {
    start: 'rgba(63, 185, 80, 0.4)',
    end: 'rgba(63, 185, 80, 0.0)',
  },
  accent: {
    start: 'rgba(0, 217, 255, 0.4)',
    end: 'rgba(0, 217, 255, 0.0)',
  },
  purple: {
    start: 'rgba(139, 92, 246, 0.4)',
    end: 'rgba(139, 92, 246, 0.0)',
  },
} as const

// Tooltip styling
export const TOOLTIP_STYLE = {
  backgroundColor: '#1C2128',
  border: '1px solid rgba(139, 146, 158, 0.3)',
  borderRadius: '8px',
  padding: '12px',
  boxShadow: '0 4px 20px rgba(0, 0, 0, 0.4)',
} as const

// Color palette for multi-series charts
export const PALETTE = [
  CHART_COLORS.primary,
  CHART_COLORS.success,
  CHART_COLORS.purple,
  CHART_COLORS.accent,
  CHART_COLORS.warning,
  CHART_COLORS.pink,
  CHART_COLORS.teal,
  CHART_COLORS.danger,
] as const

// Get color by index (cycles through palette)
export function getColorByIndex(index: number): string {
  return PALETTE[index % PALETTE.length]
}

// Format numbers for display
export function formatNumber(value: number): string {
  if (value >= 1000000) {
    return `${(value / 1000000).toFixed(1)}M`
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}K`
  }
  return value.toLocaleString()
}

// Format percentage
export function formatPercent(value: number, decimals: number = 1): string {
  return `${value.toFixed(decimals)}%`
}

// Format duration in milliseconds
export function formatDuration(ms: number): string {
  if (ms < 1000) {
    return `${Math.round(ms)}ms`
  }
  return `${(ms / 1000).toFixed(1)}s`
}
