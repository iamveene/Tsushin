'use client'

/**
 * Phase 14.5: Search Results Component
 * Displays search results with highlighting and thread navigation
 */

import React from 'react'
import { formatDateTime } from '@/lib/dateUtils'

interface SearchResult {
  // Common fields
  snippet: string
  timestamp: string

  // Message result fields
  thread_id?: number
  message_id?: string
  role?: string
  content?: string
  thread_title?: string
  agent_name?: string
  similarity?: number
  rank?: number
  match_type?: string

  // Tool execution result fields
  type?: string  // 'tool_execution' for tool results
  tool_name?: string
  command?: string
  status?: string
  execution_id?: number
  execution_time_ms?: number
}

interface SearchResultsProps {
  results: SearchResult[]
  total: number
  searchMode: string
  query: string
  onResultClick: (threadId: number, messageId: string) => void
  onLoadMore?: () => void
  hasMore?: boolean
  isLoading?: boolean
}

export default function SearchResults({
  results,
  total,
  searchMode,
  query,
  onResultClick,
  onLoadMore,
  hasMore,
  isLoading
}: SearchResultsProps) {

  const formatTimestamp = (timestamp: string) => {
    try {
      return formatDateTime(timestamp)
    } catch {
      return timestamp
    }
  }

  const getModeIcon = (match_type?: string) => {
    if (match_type === 'semantic') {
      return (
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      )
    }
    return (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    )
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="relative w-16 h-16">
          <div className="absolute inset-0 rounded-full border-4 border-tsushin-surface"></div>
          <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-tsushin-accent animate-spin"></div>
        </div>
      </div>
    )
  }

  if (results.length === 0) {
    return (
      <div className="text-center py-12">
        <svg className="w-16 h-16 mx-auto text-tsushin-slate mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <h3 className="text-lg font-medium text-white mb-2">No results found</h3>
        <p className="text-tsushin-slate">Try different keywords or search mode</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-tsushin-border">
        <div>
          <h3 className="text-lg font-medium text-white">
            {total} result{total !== 1 ? 's' : ''} found
          </h3>
          <p className="text-sm text-tsushin-slate">
            {searchMode === 'full_text' && 'Full-text search'}
            {searchMode === 'semantic' && 'Semantic search'}
            {searchMode === 'combined' && 'Combined search'}
          </p>
        </div>
      </div>

      {/* Results List */}
      <div className="space-y-3">
        {results.map((result, idx) => {
          const isToolResult = result.type === 'tool_execution'

          if (isToolResult) {
            // Tool Execution Result
            return (
              <div
                key={`tool-${idx}`}
                className="w-full text-left p-4 bg-amber-500/5 hover:bg-amber-500/10 border border-amber-500/20 rounded-lg transition-all"
              >
                {/* Header */}
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <svg className="w-4 h-4 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                    <span className="text-xs px-2 py-1 rounded bg-amber-500/20 text-amber-400">
                      {result.tool_name || 'Tool'}
                    </span>
                    <span className={`text-xs px-2 py-1 rounded ${
                      result.status === 'completed' ? 'bg-green-500/20 text-green-400' :
                      result.status === 'failed' ? 'bg-red-500/20 text-red-400' :
                      'bg-gray-500/20 text-gray-400'
                    }`}>
                      {result.status}
                    </span>
                    {result.execution_time_ms && (
                      <span className="text-xs text-tsushin-slate">
                        {result.execution_time_ms}ms
                      </span>
                    )}
                  </div>
                  <span className="text-xs text-tsushin-slate">
                    {formatTimestamp(result.timestamp)}
                  </span>
                </div>

                {/* Command */}
                {result.command && (
                  <div className="text-sm text-tsushin-slate mb-2 font-mono bg-black/20 px-2 py-1 rounded truncate">
                    $ {result.command}
                  </div>
                )}

                {/* Snippet with Highlighting */}
                <div
                  className="text-white leading-relaxed search-result-snippet text-sm"
                  dangerouslySetInnerHTML={{ __html: result.snippet }}
                />
              </div>
            )
          }

          // Message Result
          return (
            <button
              key={`msg-${idx}`}
              onClick={() => result.thread_id && result.message_id && onResultClick(result.thread_id, result.message_id)}
              className="w-full text-left p-4 bg-tsushin-deepBlue/30 hover:bg-tsushin-deepBlue/50 border border-tsushin-border rounded-lg transition-all group"
            >
              {/* Header */}
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2">
                  {getModeIcon(result.match_type)}
                  <span className={`text-xs px-2 py-1 rounded ${result.role === 'user' ? 'bg-blue-500/20 text-blue-400' : 'bg-purple-500/20 text-purple-400'}`}>
                    {result.role}
                  </span>
                  {result.agent_name && (
                    <span className="text-xs text-tsushin-slate">
                      @{result.agent_name}
                    </span>
                  )}
                  {result.similarity && (
                    <span className="text-xs text-tsushin-accent">
                      {Math.round(result.similarity * 100)}% match
                    </span>
                  )}
                </div>
                <span className="text-xs text-tsushin-slate">
                  {formatTimestamp(result.timestamp)}
                </span>
              </div>

              {/* Thread Title */}
              {result.thread_title && (
                <div className="text-sm text-tsushin-slate mb-2 flex items-center gap-2">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                  </svg>
                  {result.thread_title}
                </div>
              )}

              {/* Snippet with Highlighting */}
              <div
                className="text-white leading-relaxed search-result-snippet"
                dangerouslySetInnerHTML={{ __html: result.snippet || (result.content?.substring(0, 150) + '...') || '' }}
              />

              {/* View Thread Button */}
              <div className="mt-3 opacity-0 group-hover:opacity-100 transition-opacity">
                <span className="text-sm text-tsushin-accent flex items-center gap-1">
                  View in thread
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </span>
              </div>
            </button>
          )
        })}
      </div>

      {/* Load More */}
      {hasMore && onLoadMore && (
        <button
          onClick={onLoadMore}
          className="w-full py-3 border border-tsushin-border rounded-lg text-tsushin-slate hover:text-white hover:border-tsushin-accent transition-all"
        >
          Load more results
        </button>
      )}

      <style jsx>{`
        .search-result-snippet :global(mark) {
          background-color: rgba(99, 102, 241, 0.3);
          color: #818cf8;
          padding: 2px 4px;
          border-radius: 2px;
        }
      `}</style>
    </div>
  )
}
