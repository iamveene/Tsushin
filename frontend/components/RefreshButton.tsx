'use client'

import { useState } from 'react'

/**
 * Global Refresh Button Component
 * Icon-only with tooltip on hover
 */
export default function RefreshButton() {
  const [isRefreshing, setIsRefreshing] = useState(false)

  const handleRefresh = () => {
    setIsRefreshing(true)

    // Emit custom refresh event
    const event = new CustomEvent('tsushin:refresh', {
      detail: { timestamp: Date.now() }
    })
    window.dispatchEvent(event)

    // Reset spinning animation after 1 second
    setTimeout(() => {
      setIsRefreshing(false)
    }, 1000)
  }

  return (
    <button
      onClick={handleRefresh}
      disabled={isRefreshing}
      className={`
        group relative p-2 rounded-lg
        transition-all duration-300
        hover:bg-tsushin-surface/50
        disabled:opacity-50 disabled:cursor-not-allowed
      `}
      title="Refresh current view"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
        strokeWidth={2}
        stroke="currentColor"
        className={`w-4 h-4 text-teal-400 transition-transform duration-300
          ${isRefreshing ? 'animate-spin' : 'group-hover:rotate-45'}
        `}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99"
        />
      </svg>
    </button>
  )
}
