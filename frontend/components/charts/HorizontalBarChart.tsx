'use client'

/**
 * Horizontal Bar Chart Component
 *
 * Clean horizontal bar chart for distributions.
 * Shows values with animated fill bars.
 */

import { useMemo } from 'react'
import { CHART_COLORS, getColorByIndex, formatPercent } from './chartTheme'

interface BarData {
  name: string
  value: number
  color?: string
}

interface HorizontalBarChartProps {
  data: BarData[]
  title?: string
  showPercentage?: boolean
  showValue?: boolean
  maxBars?: number
  height?: number
  barHeight?: number
  className?: string
}

export default function HorizontalBarChart({
  data,
  title,
  showPercentage = true,
  showValue = true,
  maxBars = 5,
  height,
  barHeight = 24,
  className = '',
}: HorizontalBarChartProps) {
  const total = useMemo(
    () => data.reduce((sum, item) => sum + item.value, 0),
    [data]
  )

  const sortedData = useMemo(() => {
    return [...data]
      .sort((a, b) => b.value - a.value)
      .slice(0, maxBars)
      .map((item, index) => ({
        ...item,
        color: item.color || getColorByIndex(index),
        percentage: total > 0 ? (item.value / total) * 100 : 0,
      }))
  }, [data, maxBars, total])

  const maxValue = useMemo(
    () => Math.max(...sortedData.map((d) => d.value), 1),
    [sortedData]
  )

  if (data.length === 0 || total === 0) {
    return (
      <div className={`flex flex-col ${className}`}>
        {title && (
          <h3 className="text-sm font-semibold text-white mb-4">{title}</h3>
        )}
        <div className="text-tsushin-slate text-sm text-center py-4">
          No data available
        </div>
      </div>
    )
  }

  const calculatedHeight = height || sortedData.length * (barHeight + 16) + 40

  return (
    <div className={className} style={{ minHeight: calculatedHeight }}>
      {title && (
        <h3 className="text-sm font-semibold text-white mb-4">{title}</h3>
      )}

      <div className="space-y-3">
        {sortedData.map((item, index) => (
          <div key={item.name} className="group">
            {/* Label row */}
            <div className="flex items-center justify-between mb-1.5">
              <div className="flex items-center gap-2 min-w-0">
                <div
                  className="w-2 h-2 rounded-full flex-shrink-0"
                  style={{ backgroundColor: item.color }}
                />
                <span className="text-sm text-white truncate">{item.name}</span>
              </div>
              <div className="flex items-center gap-2 text-sm flex-shrink-0 ml-2">
                {showValue && (
                  <span className="text-white font-medium">
                    {item.value.toLocaleString()}
                  </span>
                )}
                {showPercentage && (
                  <span className="text-tsushin-slate">
                    ({formatPercent(item.percentage, 0)})
                  </span>
                )}
              </div>
            </div>

            {/* Bar */}
            <div
              className="w-full rounded-full overflow-hidden"
              style={{
                height: barHeight,
                backgroundColor: 'rgba(139, 146, 158, 0.1)',
              }}
            >
              <div
                className="h-full rounded-full transition-all duration-1000 ease-out group-hover:opacity-80"
                style={{
                  width: `${(item.value / maxValue) * 100}%`,
                  backgroundColor: item.color,
                  animation: `barGrow 1s ease-out ${index * 0.1}s both`,
                }}
              />
            </div>
          </div>
        ))}
      </div>

      <style jsx>{`
        @keyframes barGrow {
          from {
            width: 0%;
          }
        }
      `}</style>
    </div>
  )
}
