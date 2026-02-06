'use client'

/**
 * Animated Counter Component
 *
 * Displays a number that counts up smoothly from 0 to the target value.
 * Used for KPI metrics to add visual interest.
 */

import { useEffect, useRef, useState } from 'react'
import { formatNumber, formatPercent, formatDuration } from './chartTheme'

interface AnimatedCounterProps {
  value: number
  duration?: number // Animation duration in ms
  format?: 'number' | 'percent' | 'duration' | 'raw'
  decimals?: number
  suffix?: string
  prefix?: string
  className?: string
}

export default function AnimatedCounter({
  value,
  duration = 1500,
  format = 'number',
  decimals = 0,
  suffix = '',
  prefix = '',
  className = '',
}: AnimatedCounterProps) {
  const [displayValue, setDisplayValue] = useState(0)
  const startTimeRef = useRef<number | null>(null)
  const rafRef = useRef<number | null>(null)

  useEffect(() => {
    // Reset animation when value changes
    startTimeRef.current = null
    setDisplayValue(0)

    const animate = (timestamp: number) => {
      if (startTimeRef.current === null) {
        startTimeRef.current = timestamp
      }

      const elapsed = timestamp - startTimeRef.current
      const progress = Math.min(elapsed / duration, 1)

      // Easing function: ease-out cubic
      const easedProgress = 1 - Math.pow(1 - progress, 3)

      const currentValue = easedProgress * value
      setDisplayValue(currentValue)

      if (progress < 1) {
        rafRef.current = requestAnimationFrame(animate)
      } else {
        setDisplayValue(value) // Ensure we end at exact value
      }
    }

    rafRef.current = requestAnimationFrame(animate)

    return () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current)
      }
    }
  }, [value, duration])

  const formatValue = (val: number): string => {
    switch (format) {
      case 'percent':
        return formatPercent(val, decimals)
      case 'duration':
        return formatDuration(val)
      case 'raw':
        return decimals > 0 ? val.toFixed(decimals) : Math.round(val).toString()
      case 'number':
      default:
        return formatNumber(Math.round(val))
    }
  }

  return (
    <span className={className}>
      {prefix}
      {formatValue(displayValue)}
      {suffix}
    </span>
  )
}
