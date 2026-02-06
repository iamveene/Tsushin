'use client'

/**
 * Phase 15: Skill Projects - Project Context Banner
 *
 * Displays when user is in a project context.
 * Shows project name, document count, and exit button.
 */

import React from 'react'

interface ProjectContextBannerProps {
  projectName: string
  projectId: number
  documentCount?: number
  onExit: () => void
  isLoading?: boolean
}

export default function ProjectContextBanner({
  projectName,
  projectId,
  documentCount = 0,
  onExit,
  isLoading = false
}: ProjectContextBannerProps) {
  return (
    <div className="flex items-center justify-between px-4 py-2 bg-gradient-to-r from-purple-900/40 to-indigo-900/40 border-b border-purple-500/30 backdrop-blur-sm">
      <div className="flex items-center gap-3">
        {/* Project Icon */}
        <div className="w-8 h-8 rounded-lg bg-purple-500/20 flex items-center justify-center">
          <svg className="w-4 h-4 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
          </svg>
        </div>

        {/* Project Info */}
        <div className="flex flex-col">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-purple-300">
              Working in:
            </span>
            <span className="text-sm font-semibold text-white">
              {projectName}
            </span>
          </div>

          {/* Stats */}
          <div className="flex items-center gap-3 text-xs text-purple-400/70">
            <span className="flex items-center gap-1">
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              {documentCount} document{documentCount !== 1 ? 's' : ''}
            </span>
            <span>•</span>
            <span>Project ID: {projectId}</span>
          </div>
        </div>
      </div>

      {/* Exit Button */}
      <button
        onClick={onExit}
        disabled={isLoading}
        className="flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg bg-purple-500/20 hover:bg-purple-500/30 text-purple-300 hover:text-white border border-purple-500/30 hover:border-purple-500/50 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {isLoading ? (
          <>
            <svg className="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Exiting...
          </>
        ) : (
          <>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            Exit Project
          </>
        )}
      </button>
    </div>
  )
}
