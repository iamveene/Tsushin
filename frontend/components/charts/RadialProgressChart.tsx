'use client'

/**
 * Radial Progress Chart Component
 *
 * Circular gauge for displaying percentages with animation.
 * Used for success rates, completion percentages, etc.
 */

import { useEffect, useState } from 'react'
import { CHART_COLORS } from './chartTheme'

interface RadialProgressChartProps {
  value: number // 0-100
  size?: number
  strokeWidth?: number
  color?: string
  trackColor?: string
  label?: string
  showValue?: boolean
  suffix?: string
  className?: string
}

export default function RadialProgressChart({
  value,
  size = 120,
  strokeWidth = 10,
  color = CHART_COLORS.success,
  trackColor = 'rgba(139, 146, 158, 0.15)',
  label,
  showValue = true,
  suffix = '%',
  className = '',
}: RadialProgressChartProps) {
  const [animatedValue, setAnimatedValue] = useState(0)

  // Animate the value on mount and when it changes
  useEffect(() => {
    const duration = 1500
    const startTime = Date.now()
    const startValue = 0

    const animate = () => {
      const elapsed = Date.now() - startTime
      const progress = Math.min(elapsed / duration, 1)
      // Ease-out cubic
      const easedProgress = 1 - Math.pow(1 - progress, 3)
      const currentValue = startValue + (value - startValue) * easedProgress

      setAnimatedValue(currentValue)

      if (progress < 1) {
        requestAnimationFrame(animate)
      }
    }

    requestAnimationFrame(animate)
  }, [value])

  const radius = (size - strokeWidth) / 2
  const circumference = radius * 2 * Math.PI
  const strokeDashoffset = circumference - (animatedValue / 100) * circumference

  const center = size / 2

  // Determine color based on value thresholds
  const getColor = () => {
    if (value >= 90) return CHART_COLORS.success
    if (value >= 70) return CHART_COLORS.primary
    if (value >= 50) return CHART_COLORS.warning
    return CHART_COLORS.danger
  }

  const displayColor = color === CHART_COLORS.success ? getColor() : color

  return (
    <div className={`relative inline-flex flex-col items-center ${className}`}>
      <svg
        width={size}
        height={size}
        className="transform -rotate-90"
      >
        {/* Background track */}
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke={trackColor}
          strokeWidth={strokeWidth}
        />

        {/* Progress arc */}
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke={displayColor}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          className="transition-all duration-100"
          style={{
            filter: `drop-shadow(0 0 6px ${displayColor}40)`,
          }}
        />

        {/* Glow effect */}
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke={displayColor}
          strokeWidth={strokeWidth / 2}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          opacity={0.3}
          className="blur-sm"
        />
      </svg>

      {/* Center content */}
      {showValue && (
        <div
          className="absolute inset-0 flex flex-col items-center justify-center"
          style={{ transform: 'none' }}
        >
          <span className="text-2xl font-display font-bold text-white">
            {Math.round(animatedValue)}
            <span className="text-lg">{suffix}</span>
          </span>
          {label && (
            <span className="text-xs text-tsushin-slate mt-0.5">{label}</span>
          )}
        </div>
      )}
    </div>
  )
}
