'use client'

/**
 * CollapsibleNavSection - Reusable accordion section for left panel
 * Supports expand/collapse with smooth animations and preview content
 */

import React from 'react'

interface CollapsibleNavSectionProps {
  id: string
  icon: React.ReactNode
  title: string
  count?: number
  isExpanded: boolean
  onToggle: (id: string) => void
  preview?: React.ReactNode
  children: React.ReactNode
  maxHeight?: string
}

export default function CollapsibleNavSection({
  id,
  icon,
  title,
  count,
  isExpanded,
  onToggle,
  preview,
  children,
  maxHeight = 'flex-1'
}: CollapsibleNavSectionProps) {
  return (
    <div
      className={`cockpit-nav-section-accordion flex flex-col min-h-0 ${isExpanded ? 'expanded' : 'collapsed'}`}
      style={{
        flex: isExpanded ? '1' : '0 0 auto',
        minHeight: isExpanded ? '0' : 'auto'
      }}
    >
      {/* Header - Always visible and clickable */}
      <button
        onClick={() => onToggle(id)}
        className="cockpit-nav-title-accordion shrink-0 flex items-center gap-2 cursor-pointer hover:bg-[var(--pg-surface)]/30 transition-colors px-2 py-2 rounded-lg"
      >
        <span className="flex items-center justify-center w-5 h-5 text-[var(--pg-text-secondary)]">{icon}</span>
        <span className="flex-1 text-left">{title}</span>
        {count !== undefined && (
          <span className="ml-auto text-[10px] text-[var(--pg-text-muted)] font-normal">
            {count}
          </span>
        )}
        {/* Chevron indicator */}
        <svg
          className={`w-3.5 h-3.5 text-[var(--pg-text-muted)] transition-transform duration-200 ${isExpanded ? 'rotate-90' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
      </button>

      {/* Preview - Only shown when collapsed */}
      {!isExpanded && preview && (
        <div className="cockpit-nav-preview px-3 py-1.5 text-xs text-[var(--pg-text-muted)] truncate">
          {preview}
        </div>
      )}

      {/* Content - Only shown when expanded with scrolling */}
      {isExpanded && (
        <div className="flex-1 overflow-y-auto min-h-0 scrollbar-thin mt-1">
          {children}
        </div>
      )}
    </div>
  )
}
