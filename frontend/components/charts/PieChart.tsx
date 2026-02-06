'use client'

/**
 * Simple SVG Pie Chart Component
 *
 * No external dependencies - pure SVG rendering
 */

interface PieChartData {
  label: string
  value: number
  color: string
}

interface PieChartSlice {
  isFullCircle: boolean
  pathData?: string
  color: string
  label: string
  value: number
  percentage: string
  radius: number
  centerX: number
  centerY: number
}

interface PieChartProps {
  data: PieChartData[]
  size?: number
  title?: string
}

export default function PieChart({ data, size = 200, title }: PieChartProps) {
  const total = data.reduce((sum, item) => sum + item.value, 0)

  if (total === 0) {
    return (
      <div className="flex flex-col items-center justify-center" style={{ width: size, height: size }}>
        <div className="text-gray-500 dark:text-gray-400 text-sm text-center">
          No data available
        </div>
      </div>
    )
  }

  let currentAngle = -90 // Start from top

  // Calculate path coordinates (shared across all slices)
  const radius = size / 2 - 10
  const centerX = size / 2
  const centerY = size / 2

  const slices: PieChartSlice[] = data.map((item, index) => {
    const percentage = (item.value / total) * 100
    const angle = (item.value / total) * 360
    const startAngle = currentAngle
    const endAngle = currentAngle + angle
    currentAngle = endAngle

    // Handle full-circle case (360 degrees) - SVG arc cannot render when start == end point
    // Use 359.99 threshold to handle floating-point precision issues
    if (angle >= 359.99) {
      return {
        isFullCircle: true,
        color: item.color,
        label: item.label,
        value: item.value,
        percentage: percentage.toFixed(1),
        radius,
        centerX,
        centerY
      }
    }

    // Convert angles to radians
    const startRad = (startAngle * Math.PI) / 180
    const endRad = (endAngle * Math.PI) / 180

    const x1 = centerX + radius * Math.cos(startRad)
    const y1 = centerY + radius * Math.sin(startRad)
    const x2 = centerX + radius * Math.cos(endRad)
    const y2 = centerY + radius * Math.sin(endRad)

    const largeArcFlag = angle > 180 ? 1 : 0

    const pathData = [
      `M ${centerX} ${centerY}`,
      `L ${x1} ${y1}`,
      `A ${radius} ${radius} 0 ${largeArcFlag} 1 ${x2} ${y2}`,
      'Z'
    ].join(' ')

    return {
      isFullCircle: false,
      pathData,
      color: item.color,
      label: item.label,
      value: item.value,
      percentage: percentage.toFixed(1),
      radius,
      centerX,
      centerY
    }
  })

  return (
    <div className="flex flex-col items-center">
      {title && (
        <h3 className="text-sm font-semibold text-white mb-3">{title}</h3>
      )}

      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {slices.map((slice, index) => (
          <g key={index}>
            {slice.isFullCircle ? (
              <circle
                cx={slice.centerX}
                cy={slice.centerY}
                r={slice.radius}
                fill={slice.color}
                stroke="#1f2937"
                strokeWidth="2"
                className="transition-opacity hover:opacity-80 cursor-pointer"
              >
                <title>{`${slice.label}: ${slice.value} (${slice.percentage}%)`}</title>
              </circle>
            ) : (
              <path
                d={slice.pathData}
                fill={slice.color}
                stroke="#1f2937"
                strokeWidth="2"
                className="transition-opacity hover:opacity-80 cursor-pointer"
              >
                <title>{`${slice.label}: ${slice.value} (${slice.percentage}%)`}</title>
              </path>
            )}
          </g>
        ))}
      </svg>

      {/* Legend */}
      <div className="mt-4 space-y-2 w-full">
        {data.map((item, index) => (
          <div key={index} className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <div
                className="w-3 h-3 rounded-sm"
                style={{ backgroundColor: item.color }}
              ></div>
              <span className="text-white">{item.label}</span>
            </div>
            <span className="text-tsushin-slate font-medium">
              {item.value} ({((item.value / total) * 100).toFixed(1)}%)
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
