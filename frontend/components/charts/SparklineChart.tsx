'use client'

/**
 * Sparkline Chart Component
 *
 * Tiny inline chart for showing trends in KPI cards.
 * Minimalist design without axes or labels.
 */

import { useId } from 'react'
import {
  AreaChart,
  Area,
} from 'recharts'
import { CHART_COLORS, CHART_GRADIENTS } from './chartTheme'
import ResponsiveChartFrame from './ResponsiveChartFrame'

interface SparklineChartProps {
  data: number[]
  color?: keyof typeof CHART_GRADIENTS | string
  width?: number
  height?: number
  showGradient?: boolean
  className?: string
}

export default function SparklineChart({
  data,
  color = 'primary',
  width = 80,
  height = 32,
  showGradient = true,
  className = '',
}: SparklineChartProps) {
  const gradientId = `sparkline-gradient-${useId().replace(/:/g, '')}`

  if (!data || data.length === 0) {
    return (
      <div
        className={className}
        style={{ width, height }}
      />
    )
  }

  // Transform array of numbers into chart data
  const chartData = data.map((value, index) => ({
    index,
    value,
  }))

  // Get color values
  const strokeColor =
    color in CHART_COLORS
      ? CHART_COLORS[color as keyof typeof CHART_COLORS]
      : color

  return (
    <ResponsiveChartFrame className={className} width={width} height={height}>
      {({ height: chartHeight, width: chartWidth }) => (
        <AreaChart
          data={chartData}
          width={chartWidth}
          height={chartHeight}
          margin={{ top: 2, right: 2, left: 2, bottom: 2 }}
        >
          {showGradient && (
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={strokeColor} stopOpacity={0.3} />
                <stop offset="95%" stopColor={strokeColor} stopOpacity={0} />
              </linearGradient>
            </defs>
          )}
          <Area
            type="monotone"
            dataKey="value"
            stroke={strokeColor}
            strokeWidth={1.5}
            fill={showGradient ? `url(#${gradientId})` : 'transparent'}
            animationDuration={800}
            dot={false}
            activeDot={false}
          />
        </AreaChart>
      )}
    </ResponsiveChartFrame>
  )
}

/**
 * Generate mock sparkline data based on a value and trend
 * Useful when historical data isn't available
 */
export function generateSparklineData(
  finalValue: number,
  points: number = 12,
  trend: 'up' | 'down' | 'stable' = 'stable',
  variance: number = 0.2
): number[] {
  const data: number[] = []
  let baseValue: number

  switch (trend) {
    case 'up':
      baseValue = finalValue * (1 - variance * 2)
      break
    case 'down':
      baseValue = finalValue * (1 + variance * 2)
      break
    default:
      baseValue = finalValue
  }

  for (let i = 0; i < points; i++) {
    const progress = i / (points - 1)
    let value: number

    switch (trend) {
      case 'up':
        value = baseValue + (finalValue - baseValue) * progress
        break
      case 'down':
        value = baseValue - (baseValue - finalValue) * progress
        break
      default:
        value = finalValue
    }

    // Add some random variance
    const randomVariance = (Math.random() - 0.5) * 2 * variance * finalValue
    value = Math.max(0, value + randomVariance)

    data.push(value)
  }

  // Ensure the last point is close to the final value
  data[data.length - 1] = finalValue * (1 + (Math.random() - 0.5) * variance * 0.5)

  return data
}
