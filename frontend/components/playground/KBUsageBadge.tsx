'use client'

/**
 * KB Usage Badge - Shows KB usage in message responses
 * Displays which documents were used and their relevance
 */

import React, { useState } from 'react'
import { KBUsageItem } from '@/lib/client'
import { BookIcon } from '@/components/ui/icons'

interface KBUsageBadgeProps {
  kb_used: KBUsageItem[]
}

export default function KBUsageBadge({ kb_used }: KBUsageBadgeProps) {
  const [expanded, setExpanded] = useState(false)

  if (!kb_used || kb_used.length === 0) {
    return null
  }

  // Count unique documents and sources
  const uniqueDocs = new Set(kb_used.map(item => item.document_name))
  const docCount = uniqueDocs.size
  const hasAgentKB = kb_used.some(item => !item.source_type || item.source_type === 'agent')
  const hasProjectKB = kb_used.some(item => item.source_type === 'project')

  // Limit to top 3 chunks for display
  const topDocs = kb_used.slice(0, 3)
  const hasMore = kb_used.length > 3

  return (
    <div className="mt-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-[var(--pg-accent)]/10 hover:bg-[var(--pg-accent)]/20 border border-[var(--pg-accent)]/30 transition-all text-[10px] text-[var(--pg-accent)]"
        title={`Knowledge Base sources used${hasAgentKB && hasProjectKB ? ' (Agent + Project KB)' : hasProjectKB ? ' (Project KB)' : ' (Agent KB)'}`}
      >
        <BookIcon size={12} />
        <span className="font-medium">
          {docCount} doc{docCount !== 1 ? 's' : ''} used
        </span>
        {hasAgentKB && hasProjectKB && (
          <span className="text-[9px] opacity-75">(Agent + Project)</span>
        )}
        {hasProjectKB && !hasAgentKB && (
          <span className="text-[9px] opacity-75">(Project)</span>
        )}
        {hasAgentKB && !hasProjectKB && (
          <span className="text-[9px] opacity-75">(Agent)</span>
        )}
        <svg
          className={`w-3 h-3 transition-transform ${expanded ? 'rotate-180' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {expanded && (
        <div className="mt-2 p-2 rounded-lg bg-[var(--pg-surface)] border border-[var(--pg-border)] space-y-1.5 animate-fade-in">
          {topDocs.map((doc, idx) => {
            const isProjectKB = doc.source_type === 'project'
            const sourceColor = isProjectKB ? '#3b82f6' : '#06b6d4'  // blue for project, cyan for agent

            return (
              <div
                key={idx}
                className="flex items-center gap-2 p-1.5 rounded bg-[var(--pg-void)]/30"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <div
                      className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                      style={{ backgroundColor: sourceColor }}
                      title={isProjectKB ? `Project KB${doc.project_name ? `: ${doc.project_name}` : ''}` : 'Agent KB'}
                    />
                    <div className="text-[10px] font-medium text-[var(--pg-text)] truncate">
                      {doc.document_name}
                    </div>
                  </div>
                  <div className="text-[9px] text-[var(--pg-text-muted)] ml-2.5">
                    Chunk {doc.chunk_index + 1}
                    {isProjectKB && doc.project_name && (
                      <span className="ml-1 opacity-70">• {doc.project_name}</span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <div
                    className="text-[9px] font-medium"
                    style={{
                      color: doc.similarity > 0.7 ? '#10b981' : doc.similarity > 0.5 ? '#f59e0b' : '#6b7280'
                    }}
                  >
                    {Math.round(doc.similarity * 100)}%
                  </div>
                  <div
                    className="w-1.5 h-1.5 rounded-full"
                    style={{
                      backgroundColor: doc.similarity > 0.7 ? '#10b981' : doc.similarity > 0.5 ? '#f59e0b' : '#6b7280'
                    }}
                  />
                </div>
              </div>
            )
          })}

          {hasMore && (
            <div className="text-[9px] text-[var(--pg-text-muted)] text-center pt-1">
              +{kb_used.length - 3} more chunk{kb_used.length - 3 !== 1 ? 's' : ''}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
