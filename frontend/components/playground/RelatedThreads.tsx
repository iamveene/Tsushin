'use client'

/**
 * Phase 14.6: Related Threads Component
 * Displays related conversation threads with confidence scores
 */

import React from 'react'
import { api } from '@/lib/client'

interface RelatedThread {
  link_id: number
  thread_id: number
  thread_title: string
  confidence: number
  relationship_type: string
}

interface RelatedThreadsProps {
  threads: RelatedThread[]
  onThreadClick?: (threadId: number) => void
  onLinkRemoved?: () => void
}

export default function RelatedThreads({ threads, onThreadClick, onLinkRemoved }: RelatedThreadsProps) {
  const handleClick = (threadId: number) => {
    if (onThreadClick) {
      onThreadClick(threadId)
    }
  }

  const handleRemoveLink = async (e: React.MouseEvent, linkId: number) => {
    e.stopPropagation()

    if (!confirm('Remove this relationship?')) return

    try {
      await api.deleteConversationLink(linkId)
      if (onLinkRemoved) onLinkRemoved()
    } catch (err: any) {
      console.error('Failed to remove link:', err)
      alert('Failed to remove link: ' + err.message)
    }
  }

  if (threads.length === 0) {
    return null
  }

  return (
    <div>
      <h3 className="text-sm font-medium text-white mb-3 flex items-center gap-2">
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
        </svg>
        Related Conversations
      </h3>

      <div className="space-y-2">
        {threads.map(thread => (
          <div
            key={thread.thread_id}
            className="relative group"
          >
            <button
              onClick={() => handleClick(thread.thread_id)}
              className="w-full text-left p-3 bg-tsushin-deepBlue/30 hover:bg-tsushin-deepBlue/50 border border-tsushin-border rounded-lg transition-all"
            >
              {/* Thread Title */}
              <div className="flex items-start justify-between mb-1">
                <p className="text-sm text-white font-medium flex-1 group-hover:text-tsushin-accent transition-colors pr-8">
                  {thread.thread_title}
                </p>
                <svg className="w-4 h-4 text-tsushin-slate group-hover:text-tsushin-accent transition-colors flex-shrink-0 ml-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </div>

              {/* Metadata */}
              <div className="flex items-center gap-3 text-xs text-tsushin-slate">
                {/* Confidence */}
                <div className="flex items-center gap-1">
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  <span>{Math.round(thread.confidence * 100)}% similar</span>
                </div>

                {/* Relationship Type */}
                <div className="flex items-center gap-1">
                  <span className="px-2 py-0.5 bg-tsushin-surface rounded text-xs">
                    {thread.relationship_type}
                  </span>
                </div>
              </div>
            </button>

            {/* Remove Button */}
            <button
              onClick={(e) => handleRemoveLink(e, thread.link_id)}
              className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-red-500/20 rounded"
              title="Remove relationship"
            >
              <svg className="w-4 h-4 text-tsushin-slate hover:text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
