'use client'

/**
 * Area Chart Component
 *
 * Time-series area chart using Recharts with gradient fills.
 * Used for activity timeline visualization.
 */

import {
  AreaChart as RechartsAreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import {
  CHART_COLORS,
  CHART_BACKGROUND,
  CHART_GRADIENTS,
  TOOLTIP_STYLE,
} from './chartTheme'

interface AreaChartSeries {
  key: string
  name: string
  color: keyof typeof CHART_GRADIENTS | string
}

interface AreaChartProps {
  data: Record<string, any>[]
  series: AreaChartSeries[]
  xAxisKey: string
  height?: number
  showGrid?: boolean
  showLegend?: boolean
  showXAxis?: boolean
  showYAxis?: boolean
  stacked?: boolean
  className?: string
}

// Custom tooltip
const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload || !payload.length) return null

  return (
    <div style={TOOLTIP_STYLE}>
      <div className="text-tsushin-slate text-xs mb-2">{label}</div>
      {payload.map((entry: any, index: number) => (
        <div key={index} className="flex items-center gap-2 text-sm">
          <div
            className="w-2.5 h-2.5 rounded-full"
            style={{ backgroundColor: entry.color }}
          />
          <span className="text-white">{entry.name}:</span>
          <span className="text-tsushin-slate font-medium">
            {entry.value.toLocaleString()}
          </span>
        </div>
      ))}
    </div>
  )
}

// Custom legend
const CustomLegend = ({ payload }: any) => {
  if (!payload) return null

  return (
    <div className="flex justify-center gap-6 mt-2">
      {payload.map((entry: any, index: number) => (
        <div key={index} className="flex items-center gap-2 text-xs">
          <div
            className="w-2.5 h-2.5 rounded-full"
            style={{ backgroundColor: entry.color }}
          />
          <span className="text-tsushin-slate">{entry.value}</span>
        </div>
      ))}
    </div>
  )
}

export default function AreaChart({
  data,
  series,
  xAxisKey,
  height = 300,
  showGrid = true,
  showLegend = true,
  showXAxis = true,
  showYAxis = true,
  stacked = false,
  className = '',
}: AreaChartProps) {
  if (!data || data.length === 0) {
    return (
      <div
        className={`flex items-center justify-center ${className}`}
        style={{ height }}
      >
        <span className="text-tsushin-slate text-sm">No data available</span>
      </div>
    )
  }

  // Get actual color from gradient key or use directly
  const getColor = (colorKey: string): string => {
    if (colorKey in CHART_GRADIENTS) {
      return CHART_COLORS[colorKey as keyof typeof CHART_COLORS] || colorKey
    }
    return colorKey
  }

  return (
    <div className={className} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <RechartsAreaChart
          data={data}
          margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
        >
          <defs>
            {series.map((s, index) => {
              const gradientKey = s.color as keyof typeof CHART_GRADIENTS
              const gradient = CHART_GRADIENTS[gradientKey] || {
                start: `${s.color}66`,
                end: `${s.color}00`,
              }
              return (
                <linearGradient
                  key={s.key}
                  id={`gradient-${s.key}`}
                  x1="0"
                  y1="0"
                  x2="0"
                  y2="1"
                >
                  <stop offset="5%" stopColor={gradient.start} />
                  <stop offset="95%" stopColor={gradient.end} />
                </linearGradient>
              )
            })}
          </defs>

          {showGrid && (
            <CartesianGrid
              strokeDasharray="3 3"
              stroke={CHART_BACKGROUND.grid}
              vertical={false}
            />
          )}

          {showXAxis && (
            <XAxis
              dataKey={xAxisKey}
              axisLine={false}
              tickLine={false}
              tick={{ fill: CHART_COLORS.slate, fontSize: 11 }}
              dy={10}
            />
          )}

          {showYAxis && (
            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{ fill: CHART_COLORS.slate, fontSize: 11 }}
              dx={-10}
              width={40}
            />
          )}

          <Tooltip content={<CustomTooltip />} />

          {showLegend && <Legend content={<CustomLegend />} />}

          {series.map((s) => (
            <Area
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.name}
              stroke={getColor(s.color)}
              strokeWidth={2}
              fill={`url(#gradient-${s.key})`}
              stackId={stacked ? 'stack' : undefined}
              animationDuration={1000}
            />
          ))}
        </RechartsAreaChart>
      </ResponsiveContainer>
    </div>
  )
}
