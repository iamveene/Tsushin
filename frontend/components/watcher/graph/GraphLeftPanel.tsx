'use client'

/**
 * Graph Left Panel - View Options Panel
 * Phase 2: Collapsible panel with Auto-Fit toggle and layout controls
 * Phase 3: Added filter toggle for inactive agents
 * Phase 4: Added view-specific filters (archived projects)
 */

import { useState } from 'react'
import type { LayoutOptions } from './layout'
import type { GraphViewType } from './types'

interface GraphLeftPanelProps {
  viewType?: GraphViewType
  autoFit: boolean
  onAutoFitChange: (value: boolean) => void
  layoutDirection: LayoutOptions['direction']
  onLayoutDirectionChange: (direction: LayoutOptions['direction']) => void
  onRunLayout: () => void
  // Phase 3: Filter options for agents view
  showInactiveAgents?: boolean
  onShowInactiveAgentsChange?: (value: boolean) => void
  // Phase 4: Filter options for projects view
  showArchivedProjects?: boolean
  onShowArchivedProjectsChange?: (value: boolean) => void
  // Phase 5: Filter options for users view
  showInactiveUsers?: boolean
  onShowInactiveUsersChange?: (value: boolean) => void
  // Phase 7: Expand/Collapse All
  onExpandAll?: () => void
  onCollapseAll?: () => void
  hasExpandableNodes?: boolean
  hasExpandedNodes?: boolean
  isExpandingAll?: boolean
  // Phase 10: Fullscreen mode
  isMaximized?: boolean
  onToggleMaximize?: () => void
}

const LAYOUT_DIRECTIONS: { value: LayoutOptions['direction']; label: string }[] = [
  { value: 'LR', label: 'Left \u2192 Right' },
  { value: 'TB', label: 'Top \u2192 Bottom' },
  { value: 'RL', label: 'Right \u2192 Left' },
  { value: 'BT', label: 'Bottom \u2192 Top' },
]

// Inline SVG icons to match codebase patterns
const ChevronRightIcon = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
  </svg>
)

const ChevronLeftIcon = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
  </svg>
)

const ArrowsPointingInIcon = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 9V4.5M9 9H4.5M9 9L3.75 3.75M9 15v4.5M9 15H4.5M9 15l-5.25 5.25M15 9h4.5M15 9V4.5M15 9l5.25-5.25M15 15h4.5M15 15v4.5m0-4.5l5.25 5.25" />
  </svg>
)

const ArrowPathIcon = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
  </svg>
)

const EyeSlashIcon = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
  </svg>
)

const ArchiveBoxIcon = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.25 7.5l-.625 10.632a2.25 2.25 0 01-2.247 2.118H6.622a2.25 2.25 0 01-2.247-2.118L3.75 7.5M10 11.25h4M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125z" />
  </svg>
)

const UsersIcon = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
  </svg>
)

// Phase 7: Expand/Collapse icons
const ChevronDoubleRightIcon = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
  </svg>
)

const ChevronDoubleLeftIcon = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 5l7 7-7 7M5 5l7 7-7 7" />
  </svg>
)

// Phase 10: Fullscreen icons
const ArrowsPointingOutIcon = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9m5.25 11.25h-4.5m4.5 0v-4.5m0 4.5L15 15" />
  </svg>
)

const ArrowsPointingInIcon2 = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 9V4.5M9 9H4.5M9 9L3.75 3.75M9 15v4.5M9 15H4.5M9 15l-5.25 5.25M15 9h4.5M15 9V4.5M15 9l5.25-5.25M15 15h4.5M15 15v4.5m0-4.5l5.25 5.25" />
  </svg>
)

export default function GraphLeftPanel({
  viewType = 'agents',
  autoFit,
  onAutoFitChange,
  layoutDirection,
  onLayoutDirectionChange,
  onRunLayout,
  showInactiveAgents = false,
  onShowInactiveAgentsChange,
  showArchivedProjects = false,
  onShowArchivedProjectsChange,
  showInactiveUsers = false,
  onShowInactiveUsersChange,
  onExpandAll,
  onCollapseAll,
  hasExpandableNodes = false,
  hasExpandedNodes = false,
  isExpandingAll = false,
  isMaximized = false,
  onToggleMaximize,
}: GraphLeftPanelProps) {
  // Default to collapsed to save space for the graph nodes
  const [collapsed, setCollapsed] = useState(true)

  // Determine if we should show any filters
  const hasAgentsFilter = (viewType === 'agents' || viewType === 'security') && onShowInactiveAgentsChange
  const hasProjectsFilter = viewType === 'projects' && onShowArchivedProjectsChange
  const hasUsersFilter = viewType === 'users' && onShowInactiveUsersChange
  const hasAnyFilter = hasAgentsFilter || hasProjectsFilter || hasUsersFilter

  if (collapsed) {
    return (
      <div className="absolute left-2 top-2 z-10 flex gap-1">
        <button
          onClick={() => setCollapsed(false)}
          className="p-2 bg-tsushin-surface border border-tsushin-border rounded-lg hover:bg-tsushin-surface/80 transition-colors"
          title="Show view options"
        >
          <ChevronRightIcon className="w-4 h-4 text-tsushin-slate" />
        </button>
        {onToggleMaximize && (
          <button
            onClick={onToggleMaximize}
            className="p-2 bg-tsushin-surface border border-tsushin-border rounded-lg hover:bg-tsushin-surface/80 transition-colors"
            title={isMaximized ? "Exit fullscreen (Esc)" : "Fullscreen view"}
          >
            {isMaximized
              ? <ArrowsPointingInIcon2 className="w-4 h-4 text-tsushin-slate" />
              : <ArrowsPointingOutIcon className="w-4 h-4 text-tsushin-slate" />
            }
          </button>
        )}
      </div>
    )
  }

  return (
    <div className="absolute left-2 top-2 z-10 w-56 bg-tsushin-surface border border-tsushin-border rounded-lg shadow-card animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-tsushin-border">
        <span className="text-sm font-medium text-white">View Options</span>
        <div className="flex items-center gap-1">
          {onToggleMaximize && (
            <button
              onClick={onToggleMaximize}
              className="p-1 hover:bg-tsushin-deep rounded transition-colors"
              title={isMaximized ? "Exit fullscreen (Esc)" : "Fullscreen view"}
            >
              {isMaximized
                ? <ArrowsPointingInIcon2 className="w-4 h-4 text-tsushin-slate" />
                : <ArrowsPointingOutIcon className="w-4 h-4 text-tsushin-slate" />
              }
            </button>
          )}
          <button
            onClick={() => setCollapsed(true)}
            className="p-1 hover:bg-tsushin-deep rounded transition-colors"
            title="Hide panel"
          >
            <ChevronLeftIcon className="w-4 h-4 text-tsushin-slate" />
          </button>
        </div>
      </div>

      {/* Options */}
      <div className="p-3 space-y-4">
        {/* Auto-Fit Toggle */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ArrowsPointingInIcon className="w-4 h-4 text-tsushin-slate" />
            <span className="text-sm text-tsushin-slate">Auto-Fit</span>
          </div>
          <button
            onClick={() => onAutoFitChange(!autoFit)}
            role="switch"
            aria-checked={autoFit}
            className={`
              relative w-10 h-5 rounded-full transition-colors
              ${autoFit ? 'bg-tsushin-indigo' : 'bg-tsushin-deep'}
            `}
          >
            <span
              className={`
                absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform
                ${autoFit ? 'translate-x-5' : 'translate-x-0.5'}
              `}
            />
          </button>
        </div>

        {/* Layout Direction */}
        <div>
          <label className="text-sm text-tsushin-slate mb-2 block">Layout Direction</label>
          <select
            value={layoutDirection}
            onChange={(e) => onLayoutDirectionChange(e.target.value as LayoutOptions['direction'])}
            className="w-full bg-tsushin-deep border border-tsushin-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-tsushin-indigo"
          >
            {LAYOUT_DIRECTIONS.map((dir) => (
              <option key={dir.value} value={dir.value}>
                {dir.label}
              </option>
            ))}
          </select>
        </div>

        {/* Re-Layout Button */}
        <button
          onClick={onRunLayout}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-tsushin-indigo/20 hover:bg-tsushin-indigo/30 text-tsushin-indigo rounded-lg transition-colors"
        >
          <ArrowPathIcon className="w-4 h-4" />
          <span className="text-sm font-medium">Re-arrange Layout</span>
        </button>

        {/* Phase 7: Expand All / Collapse All buttons - agents and security views */}
        {(viewType === 'agents' || viewType === 'security') && (onExpandAll || onCollapseAll) && (
          <div className="flex gap-2">
            {onExpandAll && (
              <button
                onClick={onExpandAll}
                disabled={!hasExpandableNodes || isExpandingAll}
                className={`
                  flex-1 flex items-center justify-center gap-1.5 px-2 py-2 rounded-lg transition-colors text-sm
                  ${!hasExpandableNodes || isExpandingAll
                    ? 'bg-tsushin-surface/50 text-tsushin-muted cursor-not-allowed'
                    : 'bg-teal-500/20 hover:bg-teal-500/30 text-teal-400'
                  }
                `}
                title={isExpandingAll ? 'Expanding...' : 'Expand all agent nodes'}
              >
                {isExpandingAll ? (
                  <div className="w-3 h-3 border-2 border-teal-400/30 border-t-teal-400 rounded-full animate-spin" />
                ) : (
                  <ChevronDoubleLeftIcon className="w-3.5 h-3.5" />
                )}
                <span className="font-medium">Expand</span>
              </button>
            )}
            {onCollapseAll && (
              <button
                onClick={onCollapseAll}
                disabled={!hasExpandedNodes}
                className={`
                  flex-1 flex items-center justify-center gap-1.5 px-2 py-2 rounded-lg transition-colors text-sm
                  ${!hasExpandedNodes
                    ? 'bg-tsushin-surface/50 text-tsushin-muted cursor-not-allowed'
                    : 'bg-orange-500/20 hover:bg-orange-500/30 text-orange-400'
                  }
                `}
                title="Collapse all expanded nodes"
              >
                <ChevronDoubleRightIcon className="w-3.5 h-3.5" />
                <span className="font-medium">Collapse</span>
              </button>
            )}
          </div>
        )}

        {/* Filters Section - Only show if there are filters for this view */}
        {hasAnyFilter && (
          <>
            <div className="border-t border-tsushin-border pt-4">
              <span className="text-xs font-medium text-tsushin-muted uppercase tracking-wider">Filters</span>
            </div>

            {/* Show Inactive Agents Toggle - Only for Agents view */}
            {hasAgentsFilter && (
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <EyeSlashIcon className="w-4 h-4 text-tsushin-slate" />
                  <span className="text-sm text-tsushin-slate">Show Inactive</span>
                </div>
                <button
                  onClick={() => onShowInactiveAgentsChange!(!showInactiveAgents)}
                  role="switch"
                  aria-checked={showInactiveAgents}
                  className={`
                    relative w-10 h-5 rounded-full transition-colors
                    ${showInactiveAgents ? 'bg-tsushin-indigo' : 'bg-tsushin-deep'}
                  `}
                >
                  <span
                    className={`
                      absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform
                      ${showInactiveAgents ? 'translate-x-5' : 'translate-x-0.5'}
                    `}
                  />
                </button>
              </div>
            )}

            {/* Show Archived Projects Toggle - Only for Projects view */}
            {hasProjectsFilter && (
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <ArchiveBoxIcon className="w-4 h-4 text-tsushin-slate" />
                  <span className="text-sm text-tsushin-slate">Show Archived</span>
                </div>
                <button
                  onClick={() => onShowArchivedProjectsChange!(!showArchivedProjects)}
                  role="switch"
                  aria-checked={showArchivedProjects}
                  className={`
                    relative w-10 h-5 rounded-full transition-colors
                    ${showArchivedProjects ? 'bg-tsushin-indigo' : 'bg-tsushin-deep'}
                  `}
                >
                  <span
                    className={`
                      absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform
                      ${showArchivedProjects ? 'translate-x-5' : 'translate-x-0.5'}
                    `}
                  />
                </button>
              </div>
            )}

            {/* Show Inactive Users Toggle - Only for Users view */}
            {hasUsersFilter && (
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <UsersIcon className="w-4 h-4 text-tsushin-slate" />
                  <span className="text-sm text-tsushin-slate">Show Inactive</span>
                </div>
                <button
                  onClick={() => onShowInactiveUsersChange!(!showInactiveUsers)}
                  role="switch"
                  aria-checked={showInactiveUsers}
                  className={`
                    relative w-10 h-5 rounded-full transition-colors
                    ${showInactiveUsers ? 'bg-tsushin-indigo' : 'bg-tsushin-deep'}
                  `}
                >
                  <span
                    className={`
                      absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform
                      ${showInactiveUsers ? 'translate-x-5' : 'translate-x-0.5'}
                    `}
                  />
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
