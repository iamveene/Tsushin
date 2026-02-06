'use client'

/**
 * Donut Chart Component
 *
 * Modern donut chart using Recharts with center stat display.
 * More sophisticated than basic pie charts.
 */

import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import { CHART_COLORS, TOOLTIP_STYLE, getColorByIndex } from './chartTheme'

interface DonutChartData {
  name: string
  value: number
  color?: string
}

interface DonutChartProps {
  data: DonutChartData[]
  title?: string
  centerLabel?: string
  centerValue?: string | number
  size?: number
  innerRadius?: number
  outerRadius?: number
  showLegend?: boolean
  className?: string
}

// Custom tooltip component
const CustomTooltip = ({ active, payload }: any) => {
  if (!active || !payload || !payload.length) return null

  const data = payload[0]
  return (
    <div style={TOOLTIP_STYLE}>
      <div className="flex items-center gap-2">
        <div
          className="w-3 h-3 rounded-full"
          style={{ backgroundColor: data.payload.color }}
        />
        <span className="text-white font-medium">{data.name}</span>
      </div>
      <div className="text-tsushin-slate text-sm mt-1">
        {data.value.toLocaleString()} ({data.payload.percentage}%)
      </div>
    </div>
  )
}

export default function DonutChart({
  data,
  title,
  centerLabel,
  centerValue,
  size = 200,
  innerRadius = 55,
  outerRadius = 80,
  showLegend = true,
  className = '',
}: DonutChartProps) {
  const total = data.reduce((sum, item) => sum + item.value, 0)

  if (total === 0) {
    return (
      <div
        className={`flex flex-col items-center justify-center ${className}`}
        style={{ width: size, height: size + (showLegend ? 80 : 0) }}
      >
        {title && (
          <h3 className="text-sm font-semibold text-white mb-3">{title}</h3>
        )}
        <div className="text-tsushin-slate text-sm">No data available</div>
      </div>
    )
  }

  // Add percentage and color to data
  const chartData = data.map((item, index) => ({
    ...item,
    color: item.color || getColorByIndex(index),
    percentage: ((item.value / total) * 100).toFixed(1),
  }))

  return (
    <div className={`flex flex-col items-center ${className}`}>
      {title && (
        <h3 className="text-sm font-semibold text-white mb-3">{title}</h3>
      )}

      <div className="relative" style={{ width: size, height: size }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              innerRadius={innerRadius}
              outerRadius={outerRadius}
              paddingAngle={2}
              dataKey="value"
              animationDuration={1000}
              animationBegin={0}
            >
              {chartData.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={entry.color}
                  stroke="transparent"
                  className="transition-opacity hover:opacity-80 cursor-pointer"
                />
              ))}
            </Pie>
            <Tooltip content={<CustomTooltip />} />
          </PieChart>
        </ResponsiveContainer>

        {/* Center stat */}
        {(centerLabel || centerValue) && (
          <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
            {centerValue && (
              <span className="text-2xl font-display font-bold text-white">
                {centerValue}
              </span>
            )}
            {centerLabel && (
              <span className="text-xs text-tsushin-slate">{centerLabel}</span>
            )}
          </div>
        )}
      </div>

      {/* Legend */}
      {showLegend && (
        <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 w-full max-w-[220px]">
          {chartData.map((item, index) => (
            <div key={index} className="flex items-center gap-2 text-xs">
              <div
                className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                style={{ backgroundColor: item.color }}
              />
              <span className="text-white truncate">{item.name}</span>
              <span className="text-tsushin-slate ml-auto">
                {item.percentage}%
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
