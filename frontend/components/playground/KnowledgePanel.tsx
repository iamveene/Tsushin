'use client'

/**
 * Phase 14.6: Knowledge Panel Component
 * Displays extracted tags, insights, and related threads
 */

import React, { useState, useEffect } from 'react'
import { api } from '@/lib/client'
import InsightCard from './InsightCard'
import RelatedThreads from './RelatedThreads'

interface Tag {
  id: number
  tag: string
  color: string
  source: string
}

interface Insight {
  id: number
  insight_text: string
  insight_type: string
  confidence: number
}

interface RelatedThread {
  thread_id: number
  thread_title: string
  confidence: number
  relationship_type: string
}

interface KnowledgePanelProps {
  threadId: number
  agentId: number
  onClose: () => void
}

export default function KnowledgePanel({ threadId, agentId, onClose }: KnowledgePanelProps) {
  const [isExtracting, setIsExtracting] = useState(false)
  const [tags, setTags] = useState<Tag[]>([])
  const [insights, setInsights] = useState<Insight[]>([])
  const [relatedThreads, setRelatedThreads] = useState<RelatedThread[]>([])
  const [error, setError] = useState<string | null>(null)
  const [hasExtracted, setHasExtracted] = useState(false)
  const [editingTagId, setEditingTagId] = useState<number | null>(null)
  const [editingTagValue, setEditingTagValue] = useState('')

  // Load existing knowledge
  useEffect(() => {
    loadKnowledge()
  }, [threadId])

  const loadKnowledge = async () => {
    try {
      const response = await api.getThreadKnowledge(threadId)
      if (response.status === 'success') {
        setTags(response.tags || [])
        setInsights(response.insights || [])
        setRelatedThreads(response.related_threads || [])
        setHasExtracted(response.tags.length > 0 || response.insights.length > 0)
      }
    } catch (err: any) {
      console.error('Failed to load knowledge:', err)
    }
  }

  const handleExtract = async () => {
    setIsExtracting(true)
    setError(null)

    try {
      const response = await api.extractThreadKnowledge(threadId, agentId)

      if (response.status === 'success') {
        setTags(response.tags || [])
        setInsights(response.insights || [])
        setRelatedThreads(response.related_threads || [])
        setHasExtracted(true)
      } else {
        setError(response.error || 'Extraction failed')
      }
    } catch (err: any) {
      const errorMessage = err.message || 'Failed to extract knowledge'
      console.error('Knowledge extraction error:', err)
      setError(errorMessage)
    } finally {
      setIsExtracting(false)
    }
  }

  const startEditTag = (tag: Tag) => {
    setEditingTagId(tag.id)
    setEditingTagValue(tag.tag)
  }

  const saveTag = async (tagId: number) => {
    try {
      await api.updateTag(tagId, editingTagValue, null)
      setEditingTagId(null)
      loadKnowledge()
    } catch (err) {
      console.error('Failed to update tag:', err)
    }
  }

  const deleteTag = async (tagId: number) => {
    if (!confirm('Delete this tag?')) return

    try {
      await api.deleteTag(tagId)
      loadKnowledge()
    } catch (err) {
      console.error('Failed to delete tag:', err)
    }
  }

  const groupInsightsByType = () => {
    const grouped: Record<string, Insight[]> = {}
    insights.forEach(insight => {
      if (!grouped[insight.insight_type]) {
        grouped[insight.insight_type] = []
      }
      grouped[insight.insight_type].push(insight)
    })
    return grouped
  }

  const getTagColor = (color: string) => {
    const colors: Record<string, string> = {
      blue: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
      green: 'bg-green-500/20 text-green-400 border-green-500/30',
      purple: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
      orange: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
      pink: 'bg-pink-500/20 text-pink-400 border-pink-500/30',
      cyan: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
      yellow: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
      red: 'bg-red-500/20 text-red-400 border-red-500/30'
    }
    return colors[color] || colors.blue
  }

  return (
    <div className="fixed inset-y-0 right-0 w-96 bg-tsushin-surface border-l border-tsushin-border shadow-2xl z-50 flex flex-col animate-slide-left">
      {/* Header */}
      <div className="p-4 border-b border-tsushin-border flex items-center justify-between bg-tsushin-surface sticky top-0 z-10">
        <h2 className="text-lg font-semibold text-white flex items-center gap-2">
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
          Knowledge
        </h2>
        <button
          onClick={onClose}
          className="text-tsushin-slate hover:text-white transition-colors p-1 rounded hover:bg-white/10"
          title="Close panel"
          aria-label="Close knowledge panel"
        >
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {/* Extract Button */}
        {!hasExtracted && (
          <div className="text-center py-6">
            <svg className="w-16 h-16 mx-auto text-tsushin-slate mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
            <p className="text-tsushin-slate mb-4">Extract tags, insights, and related conversations using AI</p>
            <button
              onClick={handleExtract}
              disabled={isExtracting}
              className="bg-tsushin-accent text-white px-6 py-3 rounded-lg font-medium hover:bg-tsushin-accent/90 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-2 mx-auto"
            >
              {isExtracting ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                  Extracting...
                </>
              ) : (
                <>
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  Extract Knowledge
                </>
              )}
            </button>
          </div>
        )}

        {hasExtracted && (
          <button
            onClick={handleExtract}
            disabled={isExtracting}
            className="w-full text-sm text-tsushin-accent hover:text-tsushin-accent/80 py-2 border border-tsushin-border rounded hover:border-tsushin-accent transition-all disabled:opacity-50"
          >
            {isExtracting ? 'Re-extracting...' : 'Re-extract Knowledge'}
          </button>
        )}

        {error && (
          <div className="bg-red-500/20 border border-red-500/30 rounded-lg p-3 text-sm text-red-400">
            {error}
          </div>
        )}

        {/* Tags */}
        {tags.length > 0 && (
          <div>
            <h3 className="text-sm font-medium text-white mb-3 flex items-center gap-2">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
              </svg>
              Tags
            </h3>
            <div className="flex flex-wrap gap-2">
              {tags.map(tag => (
                <div key={tag.id} className="relative group">
                  {editingTagId === tag.id ? (
                    <div className="flex items-center gap-1">
                      <input
                        type="text"
                        value={editingTagValue}
                        onChange={(e) => setEditingTagValue(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') saveTag(tag.id)
                          if (e.key === 'Escape') setEditingTagId(null)
                        }}
                        className="px-2 py-1 text-sm bg-tsushin-deepBlue border border-tsushin-accent rounded text-white"
                        autoFocus
                      />
                      <button
                        onClick={() => saveTag(tag.id)}
                        className="p-1 bg-tsushin-accent rounded text-white"
                      >
                        ✓
                      </button>
                    </div>
                  ) : (
                    <span className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm border ${getTagColor(tag.color)}`}>
                      {tag.tag}
                      <span className="opacity-0 group-hover:opacity-100 transition-opacity flex gap-1">
                        <button
                          onClick={() => startEditTag(tag)}
                          className="hover:text-white"
                        >
                          ✎
                        </button>
                        <button
                          onClick={() => deleteTag(tag.id)}
                          className="hover:text-white"
                        >
                          ×
                        </button>
                      </span>
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Insights */}
        {insights.length > 0 && (
          <div>
            <h3 className="text-sm font-medium text-white mb-3 flex items-center gap-2">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
              Insights ({insights.length})
            </h3>
            <div className="space-y-3">
              {Object.entries(groupInsightsByType()).map(([type, typeInsights]) => (
                <div key={type}>
                  <h4 className="text-xs text-tsushin-slate mb-2 uppercase">{type.replace('_', ' ')}</h4>
                  {typeInsights.map(insight => (
                    <InsightCard
                      key={insight.id}
                      insight={insight}
                      onInsightUpdated={loadKnowledge}
                      onInsightDeleted={loadKnowledge}
                    />
                  ))}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Related Threads */}
        {relatedThreads.length > 0 && (
          <RelatedThreads
            threads={relatedThreads}
            onLinkRemoved={loadKnowledge}
          />
        )}
      </div>
    </div>
  )
}
