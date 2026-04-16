'use client'

import { type CSSProperties, type ReactNode, useLayoutEffect, useRef, useState } from 'react'

interface ChartFrameDimensions {
  height: number
  width: number
}

interface ResponsiveChartFrameProps {
  children: ReactNode | ((dimensions: ChartFrameDimensions) => ReactNode)
  className?: string
  fallback?: ReactNode
  height?: number | string
  minReadyHeight?: number
  minReadyWidth?: number
  width?: number | string
}

export default function ResponsiveChartFrame({
  children,
  className = '',
  fallback = null,
  height = '100%',
  minReadyHeight = 16,
  minReadyWidth = 16,
  width = '100%',
}: ResponsiveChartFrameProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const frameRef = useRef<number | null>(null)
  const [dimensions, setDimensions] = useState<ChartFrameDimensions | null>(null)

  useLayoutEffect(() => {
    const container = containerRef.current
    if (!container) {
      return
    }

    const updateDimensions = () => {
      const rect = container.getBoundingClientRect()
      const nextWidth = Math.floor(rect.width)
      const nextHeight = Math.floor(rect.height)

      if (nextWidth < minReadyWidth || nextHeight < minReadyHeight) {
        setDimensions((prev) => (prev === null ? prev : null))
        return
      }

      setDimensions((prev) => {
        if (prev && prev.width === nextWidth && prev.height === nextHeight) {
          return prev
        }

        return {
          width: nextWidth,
          height: nextHeight,
        }
      })
    }

    updateDimensions()

    if (typeof ResizeObserver === 'undefined') {
      return
    }

    const observer = new ResizeObserver(() => {
      if (frameRef.current !== null) {
        cancelAnimationFrame(frameRef.current)
      }
      frameRef.current = requestAnimationFrame(updateDimensions)
    })

    observer.observe(container)

    return () => {
      observer.disconnect()
      if (frameRef.current !== null) {
        cancelAnimationFrame(frameRef.current)
      }
    }
  }, [minReadyHeight, minReadyWidth])

  const style: CSSProperties = {
    height,
    width,
  }

  return (
    <div ref={containerRef} className={className} style={style}>
      {dimensions
        ? typeof children === 'function'
          ? children(dimensions)
          : children
        : fallback}
    </div>
  )
}
