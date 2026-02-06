'use client'

import { useState } from 'react'

/**
 * Global Refresh Button Component
 * Premium UI with gradient background and spin animation
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
        group relative flex items-center gap-2 px-3.5 py-2 rounded-lg
        font-medium text-sm transition-all duration-300
        bg-gradient-to-r from-teal-500/10 to-cyan-400/10
        border border-teal-500/30
        hover:from-teal-500/20 hover:to-cyan-400/20
        hover:border-teal-500/50 hover:shadow-glow-sm
        disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:shadow-none
      `}
      title="Refresh current view"
    >
      {/* Refresh Icon SVG with rotation animation */}
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
      <span className="text-teal-400 group-hover:text-teal-300 transition-colors">
        Refresh
      </span>
    </button>
  )
}
